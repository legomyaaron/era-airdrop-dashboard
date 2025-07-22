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

# In-memory cache
query_count = 0
cache_storage = {}
CACHE_HOURS = 24

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

# Query function with caching
async def query_era_airdrop_data(wallet_address: str) -> Dict[str, Any]:
    cache_key = wallet_address.lower()
    current_time = datetime.now()
    
    # Check cache
    if cache_key in cache_storage:
        cached_time, cached_data = cache_storage[cache_key]
        if current_time - cached_time < timedelta(hours=CACHE_HOURS):
            logging.info(f"Cached data for {wallet_address}")
            cached_data['_cached'] = True
            return cached_data
    
    # Fresh query
    logging.info(f"Fresh query for {wallet_address}")
    
    try:
        ERA_QUERY_ID = 5515686
        
        if not dune:
            result = {
                "wallet_address": wallet_address,
                "is_claimed": False,
                "claimed_amount": 0,
                "vested_amount": 0,
                "total_allocation": 0,
                "pre_claim_status": False,
                "vesting_end_date": None,
                "days_left_vesting": 0,
                "claim_transaction_hash": None,
                "_cached": False
            }
            cache_storage[cache_key] = (current_time, result)
            return result
        
        from dune_client.types import QueryParameter
        from dune_client.query import QueryBase
        
        query = QueryBase(
            name="Era Query",
            query_id=ERA_QUERY_ID,
            params=[QueryParameter.text_type(name="wallet_address", value=cache_key)]
        )
        
        result = dune.run_query(query)
        
        # Get rows
        rows = []
        if hasattr(result, 'result') and hasattr(result.result, 'rows'):
            rows = result.result.rows
        elif hasattr(result, 'get_rows'):
            rows = result.get_rows()
        
        # Process data
        if not rows:
            data = {
                "wallet_address": wallet_address,
                "is_claimed": False,
                "claimed_amount": 0,
                "vested_amount": 0,
                "total_allocation": 0,
                "pre_claim_status": False,
                "vesting_end_date": None,
                "days_left_vesting": 0,
                "claim_transaction_hash": None,
                "_cached": False
            }
        else:
            row = rows[0]
            total_allocation = float(row.get('total_allocation', 0))
            claimed_amount = float(row.get('claimed_amount', 0))
            is_claimed = bool(row.get('is_claimed', False))
            pre_claim_status = bool(row.get('pre_claim_status', False))
            claim_tx = row.get('claim_transaction_hash')
            vesting_end = row.get('vesting_end_date')
            
            days_left = 0
            vesting_date = None
            
            if vesting_end:
                try:
                    if isinstance(vesting_end, str):
                        vesting_date = datetime.fromisoformat(vesting_end.replace('Z', '+00:00'))
                    elif isinstance(vesting_end, (int, float)):
                        vesting_date = datetime.fromtimestamp(vesting_end)
                    
                    if vesting_date:
                        days_left = max(0, (vesting_date - datetime.now()).days)
                except Exception as e:
                    logging.warning(f"Date parsing error: {e}")
            
            data = {
                "wallet_address": wallet_address,
                "is_claimed": is_claimed,
                "claimed_amount": claimed_amount,
                "vested_amount": 0,
                "total_allocation": total_allocation,
                "pre_claim_status": pre_claim_status,
                "vesting_end_date": vesting_date,
                "days_left_vesting": days_left,
                "claim_transaction_hash": claim_tx,
                "_cached": False
            }
        
        # Cache result
        cache_storage[cache_key] = (current_time, data)
        return data
        
    except Exception as e:
        logging.error(f"Query error: {e}")
        data = {
            "wallet_address": wallet_address,
            "is_claimed": False,
            "claimed_amount": 0,
            "vested_amount": 0,
            "total_allocation": 0,
            "pre_claim_status": False,
            "vesting_end_date": None,
            "days_left_vesting": 0,
            "claim_transaction_hash": None,
            "_cached": False
        }
        cache_storage[cache_key] = (current_time, data)
        return data

# Routes
@app.get("/")
async def serve_frontend():
    return FileResponse('index.html')

@api_router.get("/")
async def root():
    return {"message": "Era Airdrop Dashboard API", "status": "operational"}

@api_router.get("/airdrop/{wallet_address}", response_model=AirdropResponse)
async def get_airdrop_data(wallet_address: str):
    global query_count
    
    if not is_address(wallet_address):
        return AirdropResponse(
            success=False, 
            data=None, 
            message="Invalid Ethereum wallet address format"
        )
    
    try:
        data_dict = await query_era_airdrop_data(wallet_address.lower())
        was_cached = data_dict.pop('_cached', False)
        query_count += 1
        
        message = "Data retrieved successfully"
        if was_cached:
            message += " (cached - instant!)"
        else:
            message += " (fresh from blockchain)"
        
        return AirdropResponse(
            success=True, 
            data=AirdropData(**data_dict), 
            message=message
        )
    except Exception as e:
        return AirdropResponse(
            success=False, 
            data=None, 
            message=f"Failed to retrieve airdrop data: {str(e)}"
        )

@api_router.get("/stats")
async def get_stats():
    cache_count = len(cache_storage)
    return {
        "total_queries": query_count,
        "cached_addresses": cache_count,
        "cache_hours": CACHE_HOURS,
        "status": "operational"
    }

# Setup
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

logging.basicConfig(level=logging.INFO)

@app.on_event("startup")
async def startup_event():
    logging.info("Era Airdrop Dashboard API started with caching!")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
