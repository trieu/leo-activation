import os
import random
import uuid
import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from dataclasses import dataclass, replace
from typing import Tuple, List, Dict

# =========================================================
# 1. API CONFIGURATION & SETUP
# =========================================================

app_data_enrichment = FastAPI(
    title="Christian RL Simulation API",
    description="API Service for Human Soul Simulation, compatible with LEO CDP framework profiles.",
    version="1.0.0"
)

REPORT_DIR = "test_reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# =========================================================
# 2. DATA MODELS & META (Refactored per requirements)
# =========================================================

class HumanSoulMeta(BaseModel):
    """
    Metadata configuration acting as the source of truth for the simulation.
    Allows dynamic override of events, theology_models, hyperparameters, and colors.
    """
    events: List[str] = ["SUCCESS", "FAILURE", "TEMPTATION", "CRISIS", "REFLECTION", "GRACE"]
    theology_models: List[str] = ["PAUL", "AUGUSTINE", "AQUINAS", "LUTHER", "CALVIN", "SCHLEIERMACHER", "BARTH"]
    hyperparameters: Dict[str, float] = {
        "steps": 2000.0,
        "alpha": 0.1,
        "gamma": 0.95,
        "epsilon": 0.3,
        "epsilon_decay": 0.999,
        "epsilon_min": 0.05
    }
    colors: Dict[str, str] = {
        "faith": "#4F46E5",
        "sin": "#EF4444",
        "discipline": "#10B981",
        "reason": "#8B5CF6",
        "emotion": "#F59E0B",
        "reward": "#06B6D4"
    }

class HumanProfileInput(BaseModel):
    """Input payload representing a human profile (e.g., from LEO CDP)."""
    name: str
    faith: float = Field(0.5, ge=0.0, le=1.0)
    sin_level: float = Field(0.5, ge=0.0, le=1.0)
    reason: float = Field(0.5, ge=0.0, le=1.0)
    emotion: float = Field(0.5, ge=0.0, le=1.0)
    discipline: float = Field(0.5, ge=0.0, le=1.0)
    meta: HumanSoulMeta = Field(default_factory=HumanSoulMeta)


@dataclass(frozen=True)
class Human:
    """Immutable representation of the human internal state."""
    name: str
    faith: float = 0.5
    sin_level: float = 0.5
    reason: float = 0.5
    emotion: float = 0.5
    discipline: float = 0.5

    def clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

@dataclass(frozen=True)
class Superego:
    love: float = 1.0
    purity: float = 1.0
    truth: float = 1.0
    fidelity: float = 1.0


# =========================================================
# 3. SIMULATION ENGINE 
# =========================================================

class MathUtils:
    @staticmethod
    def smooth_emotion(prev: float, new: float) -> float:
        return 0.7 * prev + 0.3 * new

class LifeEventEngine:
    @classmethod
    def apply(cls, h: Human, meta: HumanSoulMeta) -> Tuple[Human, str]:
        """Loads valid events dynamically from HumanSoulMeta."""
        event = random.choice(meta.events)
        resilience = h.emotion

        if event == "SUCCESS":
            new_em = h.clamp(MathUtils.smooth_emotion(h.emotion, h.emotion + 0.1))
            new_disc = h.clamp(h.discipline + 0.1 * resilience)
            return replace(h, emotion=new_em, discipline=new_disc), event

        elif event == "FAILURE":
            new_em = h.clamp(MathUtils.smooth_emotion(h.emotion, h.emotion - 0.2))
            new_sin = h.clamp(h.sin_level + (1 - resilience) * 0.2)
            return replace(h, emotion=new_em, sin_level=new_sin), event

        elif event == "TEMPTATION":
            new_sin = h.clamp(h.sin_level + (1 - resilience) * 0.25)
            new_reason = h.clamp(h.reason - 0.05)
            return replace(h, sin_level=new_sin, reason=new_reason), event

        elif event == "CRISIS":
            new_em = h.clamp(MathUtils.smooth_emotion(h.emotion, h.emotion - 0.3))
            new_faith = h.clamp(h.faith - 0.1)
            return replace(h, emotion=new_em, faith=new_faith), event

        elif event == "REFLECTION":
            return replace(h, reason=h.clamp(h.reason + 0.1), sin_level=h.clamp(h.sin_level - 0.1)), event

        elif event == "GRACE":
            return replace(h, faith=h.clamp(h.faith + 0.2), reason=h.clamp(h.reason + 0.05)), event

        # Fallback if unknown event is passed in meta
        return h, "NONE"

class ThinkerCatalog:
    @staticmethod
    def apply_action(h: Human, action: str) -> Human:
        stability = 1 - abs(h.emotion - 0.5)

        actions_dict = {
            "PAUL": lambda: replace(h, faith=h.clamp(h.faith + 0.12)),
            "AUGUSTINE": lambda: replace(h, sin_level=h.clamp(h.sin_level - 0.1)),
            "AQUINAS": lambda: replace(h, reason=h.clamp(h.reason + 0.1 * stability)),
            "LUTHER": lambda: replace(h, faith=h.clamp(h.faith + 0.15)),
            "CALVIN": lambda: replace(h, discipline=h.clamp(h.discipline + 0.15)),
            "SCHLEIERMACHER": lambda: replace(h, emotion=h.clamp(MathUtils.smooth_emotion(h.emotion, 0.5))),
            "BARTH": lambda: replace(h, faith=h.clamp(h.faith + 0.2)) if random.random() > 0.5 else replace(h, sin_level=h.clamp(h.sin_level - 0.2))
        }
        return actions_dict.get(action, lambda: h)()

class SimulationEnvironment:
    def __init__(self, meta: HumanSoulMeta):
        """Loads Hyperparameters from HumanSoulMeta."""
        self.ideal = Superego()
        self.meta = meta

    def _apply_cognitive_drift(self, h: Human) -> Human:
        instability = abs(h.emotion - 0.5)
        return replace(h, reason=h.clamp(h.reason - instability * 0.05))

    def _calculate_reward(self, h: Human) -> float:
        emotion_balance = 1 - abs(h.emotion - 0.5)
        return (0.25 * h.faith +
                0.25 * (1 - h.sin_level) +
                0.20 * h.discipline +
                0.10 * h.reason +
                0.20 * emotion_balance)

    def step(self, h: Human, action: str) -> Tuple[Human, str, float]:
        h_after_event, event_name = LifeEventEngine.apply(h, self.meta)
        h_after_drift = self._apply_cognitive_drift(h_after_event)
        h_final = ThinkerCatalog.apply_action(h_after_drift, action)
        reward = self._calculate_reward(h_final)
        return h_final, event_name, reward

# =========================================================
# 4. RL AGENT & TRAINER
# =========================================================

class QLearningAgent:
    def __init__(self, meta: HumanSoulMeta):
        self.q_table: Dict[Tuple, Dict[str, float]] = {}
        self.theology_models = meta.theology_models
        # Load hyperparams from meta
        self.alpha = meta.hyperparameters.get("alpha", 0.1)
        self.gamma = meta.hyperparameters.get("gamma", 0.95)
        self.epsilon = meta.hyperparameters.get("epsilon", 0.3)
        self.epsilon_decay = meta.hyperparameters.get("epsilon_decay", 0.999)
        self.epsilon_min = meta.hyperparameters.get("epsilon_min", 0.05)

    def _get_state_tuple(self, h: Human) -> Tuple:
        return (round(h.faith, 1), round(h.sin_level, 1), round(h.discipline, 1), round(h.emotion, 1))

    def _ensure_state(self, state: Tuple):
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.theology_models}

    def choose_action(self, h: Human) -> str:
        state = self._get_state_tuple(h)
        self._ensure_state(state)
        if random.random() < self.epsilon:
            return random.choice(self.theology_models)
        return max(self.q_table[state], key=self.q_table[state].get)

    def learn(self, old_h: Human, action: str, reward: float, new_h: Human):
        s1 = self._get_state_tuple(old_h)
        s2 = self._get_state_tuple(new_h)
        self._ensure_state(s2)

        best_next_q = max(self.q_table[s2].values())
        current_q = self.q_table[s1][action]

        self.q_table[s1][action] += self.alpha * (reward + self.gamma * best_next_q - current_q)
        self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)


class SimulationTrainer:
    def __init__(self, meta: HumanSoulMeta):
        self.meta = meta
        self.steps = int(meta.hyperparameters.get("steps", 2000))
        # Actions load naturally via meta being passed
        self.agent = QLearningAgent(meta)
        self.env = SimulationEnvironment(meta)

    def run(self, subject: Human) -> pd.DataFrame:
        logs = []
        current_subject = subject

        for step in range(self.steps):
            action = self.agent.choose_action(current_subject)
            next_subject, event, reward = self.env.step(current_subject, action)
            self.agent.learn(current_subject, action, reward, next_subject)

            logs.append({
                "step": step, "name": next_subject.name,
                "faith": next_subject.faith, "sin": next_subject.sin_level,
                "discipline": next_subject.discipline, "reason": next_subject.reason,
                "emotion": next_subject.emotion, "reward": reward,
                "event": event, "action": action
            })

            current_subject = next_subject

        return pd.DataFrame(logs)


# =========================================================
# 5. VISUALIZATION (Saved to File)
# =========================================================

class DashboardGenerator:
    FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"

    def __init__(self, df: pd.DataFrame, meta: HumanSoulMeta, filename: str):
        self.df = df
        self.filename = filename
        self.meta = meta
        self.colors = self.meta.colors  # Load colors from HumanSoulMeta

        self.action_stats = self.df.groupby('action')['reward'].agg(['mean', 'count']).reset_index()
        self.best_action = self.action_stats.sort_values(by='mean', ascending=False).iloc[0]['action']

        self.fig = make_subplots(
            rows=5, cols=2,
            subplot_titles=(
                "Faith ✝️<br>", "Sin ⚠️<br>", "Discipline 🛡️<br>",
                "Reason 🧠<br>", "Emotion 🕊️<br>", "Overall Health ✨<br>",
                "Soul Personality 🕸️<br>", "AI Strategy 📊<br>"
            ),
            specs=[
                [{"type": "xy"}, {"type": "xy"}],
                [{"type": "xy"}, {"type": "xy"}],
                [{"type": "xy"}, {"type": "xy"}],
                [{"type": "polar", "colspan": 2}, None],
                [{"type": "domain", "colspan": 2}, None]
            ],
            vertical_spacing=0.08
        )

    def _add_line_charts(self):
        metrics = [('faith', 1, 1), ('sin', 1, 2), ('discipline', 2, 1),
                   ('reason', 2, 2), ('emotion', 3, 1), ('reward', 3, 2)]

        for col, r, c in metrics:
            color = self.colors.get(col, "#000000")
            fillcolor = color.replace(')', ', 0.1)').replace('#', 'rgba(') if '#' not in color else 'rgba(0,0,0,0)'

            self.fig.add_trace(
                go.Scatter(
                    x=self.df.step, y=self.df[col], name=col.capitalize(),
                    line=dict(color=color, width=2), fill='tozeroy', fillcolor=fillcolor,
                    showlegend=False, mode='lines'
                ), row=r, col=c
            )

    def _add_radar_chart(self):
        categories = ['Đức tin', 'Lý trí', 'Kỷ luật', 'Nội tâm', 'Thanh sạch']
        categories_plot = categories + [categories[0]]

        def extract(row):
            vals = [row['faith'], row['reason'], row['discipline'],
                    1 - abs(row['emotion'] - 0.5) * 2, 1 - row['sin']]
            return vals + [vals[0]]

        val_init = extract(self.df.iloc[0])
        val_final = extract(self.df.iloc[-1])
        val_ideal = [1.0] * 6

        self.fig.add_trace(go.Scatterpolar(r=val_ideal, theta=categories_plot, fill='toself', name='Ideal Target',
                           line=dict(color='#EAB308', width=2, dash='dot'), fillcolor='rgba(234, 179, 8, 0.1)'), row=4, col=1)
        self.fig.add_trace(go.Scatterpolar(r=val_init, theta=categories_plot, fill='toself', name='Start State',
                           line=dict(color='#94A3B8', width=2), fillcolor='rgba(148, 163, 184, 0.2)'), row=4, col=1)
        self.fig.add_trace(go.Scatterpolar(r=val_final, theta=categories_plot, fill='toself', name='Final State',
                           line=dict(color=self.colors.get('reward', '#06B6D4'), width=3), fillcolor='rgba(6, 182, 212, 0.3)'), row=4, col=1)

        self.fig.update_polars(radialaxis=dict(range=[0, 1], showline=False))

    def _add_pie_chart(self):
        self.fig.add_trace(
            go.Pie(
                labels=self.action_stats['action'], values=self.action_stats['count'], hole=0.5, textinfo='percent',
                marker=dict(colors=['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']),
            ), row=5, col=1
        )

    def _configure_layout(self):
        reward_color = self.colors.get('reward', '#06B6D4')
        self.fig.update_layout(
            height=1600,
            title=dict(text=f"<b>AI Dashboard</b> | Best Strategy: <span style='color:{reward_color}'>{self.best_action}</span>",
                       font=dict(size=24, family=self.FONT_FAMILY), x=0.5, xanchor='center'),
            template="plotly_white", font=dict(family=self.FONT_FAMILY, color='#1E293B'),
            hovermode="x unified", showlegend=True, margin=dict(t=100, b=100, l=40, r=40)
        )

    def save_html(self) -> str:
        """Generates Plotly HTML and saves it to the reports directory."""
        self._add_line_charts()
        self._add_radar_chart()
        self._add_pie_chart()
        self._configure_layout()

        html_str = self.fig.to_html(include_plotlyjs="cdn", full_html=True)
        filepath = os.path.join(REPORT_DIR, self.filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_str)
            
        return self.filename

# =========================================================
# 6. FASTAPI ENDPOINTS
# =========================================================

@app_data_enrichment.post("/api/v1/simulate")
def run_simulation(profile: HumanProfileInput):
    """
    1) Input: Human profile data (Compatible with LEO CDP payload structure).
    2) Output: JSON containing the generated HTML report filename.
    """
    
    # Map Pydantic Input to Internal Immutable Dataclass
    subject = Human(
        name=profile.name,
        faith=profile.faith,
        sin_level=profile.sin_level,
        discipline=profile.discipline,
        reason=profile.reason,
        emotion=profile.emotion
    )

    # Initialize Trainer with Metadata
    trainer = SimulationTrainer(meta=profile.meta)
    df_results = trainer.run(subject=subject)

    # Generate Dashboard and save file
    report_filename = f"report_{subject.name}_{uuid.uuid4().hex[:8]}.html"
    dashboard = DashboardGenerator(df_results, meta=profile.meta, filename=report_filename)
    saved_file = dashboard.save_html()

    return {
        "status": "success",
        "message": f"Simulation completed for {subject.name}.",
        "report_filename": saved_file,
        "report_url": f"/api/v1/reports/{saved_file}"
    }


@app_data_enrichment.get("/api/v1/reports/{filename}", response_class=HTMLResponse)
def get_report(filename: str):
    """
    HTML file handler: Receives filename and returns rendered HTML.
    """
    filepath = os.path.join(REPORT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report file not found.")
        
    with open(filepath, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    return html_content