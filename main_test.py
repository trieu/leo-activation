import uvicorn

from core.main_configs import MAIN_APP_HOST, MAIN_APP_PORT

## Uvicorn runner (runtime only) for local development and testing
if __name__ == "__main__":
    uvicorn.run(
       "tests.test_profile_enrichment:app_data_enrichment",
        host=MAIN_APP_HOST,
        port=MAIN_APP_PORT,
        reload=True,
    )