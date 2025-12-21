import os
import re
import torch
import logging
from dotenv import load_dotenv
from transformers import AutoProcessor, AutoModelForCausalLM
from huggingface_hub import login
from agentic_models.base import BaseLLMEngine

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LEO-CDP-Engine")

load_dotenv(override=True)

# Recommended for local function calling
DEFAULT_MODEL_ID = os.getenv("DEFAULT_MODEL_ID", "google/functiongemma-270m-it")

class FunctionGemmaEngine(BaseLLMEngine):
    def __init__(self, model_id: str = DEFAULT_MODEL_ID):
        super().__init__()
        self.model_id = model_id
        
        if os.getenv("HF_TOKEN"):
            login(token=os.getenv("HF_TOKEN"))

        logger.info(f"Loading local model: {self.model_id}")
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        
        # Performance optimization: Use 4-bit quantization if available for 270M performance
        # or stick to bfloat16 for accuracy on A100/H100/RTX 3090+
        torch_dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            device_map="auto",
            torch_dtype=torch_dtype,
            trust_remote_code=True
        ).eval()

    def extract_tool_calls(self, text: str):
        """
        Improved extraction for LEO CDP. 
        Handles:
        1. Truncated outputs (missing <end_function_call>).
        2. Multi-line arguments and nested commas.
        3. Type-safe casting for LEO activation parameters.
        """
        
        # 1. Pre-processing: Auto-fix truncated tags (common in 270M models)
        if "<start_function_call>" in text and "<end_function_call>" not in text:
            text += "}<end_function_call>"

        def cast_value(v: str):
            v = v.strip()
            # Handle LEO-specific booleans
            if v.lower() in ("true", "false"):
                return v.lower() == "true"
            # Handle Numeric IDs/Counts
            try:
                if '.' in v: return float(v)
                return int(v)
            except ValueError:
                # Clean strings and handle the <escape> protocol used by FunctionGemma
                return v.replace("<escape>", "").strip("'\" ")

        calls = []
        
        # Regex designed for the FunctionGemma control tokens: 
        # <start_function_call>call:func_name{key:val}<end_function_call>
        pattern = r"<start_function_call>call:(\w+)\{(.*?)\}(?:<end_function_call>|$)"
        
        for name, args_block in re.findall(pattern, text, re.DOTALL):
            parsed_args = {}
            
            # This sub-pattern extracts 'key:value' pairs while respecting <escape> blocks
            # which FunctionGemma uses for strings containing commas or special characters.
            arg_pairs = re.findall(r"(\w+):(?:<escape>(.*?)<escape>|([^,}]*))", args_block)
            
            for k, v_escaped, v_raw in arg_pairs:
                val = v_escaped if v_escaped else v_raw
                parsed_args[k] = cast_value(val)

            calls.append({
                "name": name,
                "arguments": parsed_args
            })

        return calls

    def generate(self, messages, tools=None) -> str:
        """
        Generates structured tool calls with specific constraints for 
        FunctionGemma accuracy.
        """
        # Ensure the system/developer prompt explicitly mentions LEO CDP context
        # to ground the 270M model.
        
        inputs = self.processor.apply_chat_template(
            messages,
            tools=tools,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device)

        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=512, # Increased for complex segmentation queries
                pad_token_id=self.processor.eos_token_id,
                # Accuracy Boost: Greedy search (do_sample=False) is better for tool calling
                do_sample=False, 
                # Frequency penalty helps prevent the 270M model from looping XML tags
                repetition_penalty=1.1 
            )

        gen_tokens = output[0][inputs["input_ids"].shape[1]:]
        decoded = self.processor.decode(gen_tokens, skip_special_tokens=True)
        
        # Post-processing: ensure XML tags are balanced (Gemma 270M sometimes cuts off)
        if "<start_function_call>" in decoded and "<end_function_call>" not in decoded:
            decoded += "}<end_function_call>"
            
        return decoded