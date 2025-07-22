from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import os
import logging
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dune_client.client import DuneClient
from eth_utils import is_address

# Load environment variables
load_dotenv()

# Dune client
dune_api_key = os.environ.get('DUNE_API_KEY')
dune = DuneClient(dune_api_key) if dune_api_key else None

app = FastAPI(title="Era Airdrop Dashboard API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# In-memory stats counter and cache
query_count = 0
cache_storage = {}
CACHE_DURATION_HOURS = 24  # 24 hours cache

# Models
class AirdropData(BaseModel):
    wallet_address: str
    is_claimed: bool
    claimed_amount: float
    vested_amount: float
    total_allocation: float
    pre_claim_status: bool
    vesting_end_date: Optional[datetime]
    days_left_vesting: Optional[int]
    claim_transaction_hash: Optional[str]

class AirdropResponse(BaseModel):
    success: bool
    data: Optional[AirdropData]
    message: str

# Dune query function with 24-hour caching
async def query_era_airdrop_data(wallet_address: str) -> Dict[str, Any]:
    cache_key = wallet_address.lower()
    current_time = datetime.now()
    was_cached = False

    # Check for cached data (24 hours)
    if cache_key in cache_storage:
        cached_time, cached_data = cache_storage[cache_key]
        if current_time - cached_time < timedelta(hours=CACHE_DURATION_HOURS):
            logging.info(f"⚡ Returning cached data for {wallet_address} (cached {(current_time - cached_time).seconds // 3600}h ago)")
            was_cached = True
            cached_data['_was_cached'] = True
            return cached_data

    # Run fresh Dune query
    logging.info(f"🔍 Running fresh Dune query for {wallet_address} (this may take 30+ seconds)")

    try:
        ERA_AIRDROP_QUERY_ID = 5515686

        if not dune:
            logging.warning("Dune client not initialized")
            result = {
                "wallet_address": wallet_address, "is_claimed": False, "claimed_amount": 0,
                "vested_amount": 0, "total_allocation": 0, "pre_claim_status": False,
                "vesting_end_date": None, "days_left_vesting": 0, "claim_transaction_hash": None,
                "_was_cached": False
            }
            cache_storage[cache_key] = (current_time, result)
            return result

        from dune_client.types import QueryParameter
        from dune_client.query import QueryBase

        query = QueryBase(
            name="Era Airdrop Query",
            query_id=ERA_AIRDROP_QUERY_ID,
            params=[QueryParameter.text_type(name="wallet_address", value=wallet_address.lower())]
        )

        result = dune.run_query(query)

        if hasattr(result, 'result') and hasattr(result.result, 'rows'):
            rows = result.result.rows
        elif hasattr(result, 'get_rows'):
            rows = result.get_rows()
        else:
            rows = []

        if not rows:
            result_data = {
                "wallet_address": wallet_address, "is_claimed": False, "claimed_amount": 0,
                "vested_amount": 0, "total_allocation": 0, "pre_claim_status": False,
                "vesting_end_date": None, "days_left_vesting": 0, "claim_transaction_hash": None,
                "_was_cached": False
            }
            cache_storage[cache_key] = (current_time, result_data)
            return result_data

        row = rows[0
