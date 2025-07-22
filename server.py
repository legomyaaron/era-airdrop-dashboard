from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
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

# In-memory stats counter
query_count = 0

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

# Dune query function
async def query_era_airdrop_data(wallet_address: str) -> Dict[str, Any]:
    try:
        ERA_AIRDROP_QUERY_ID = 5515686
        
        if not dune:
            logging.warning("Dune client not initialized")
            return {
                "wallet_address": wallet_address, "is_claimed": False, "claimed_amount": 0,
                "vested_amount": 0, "total_allocation": 0, "pre_claim_status": False,
                "vesting_end_date": None, "days_left_vesting": 0, "claim_transaction_hash": None
            }
        
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
            return {
                "wallet_address": wallet_address, "is_claimed": False, "claimed_amount": 0,
                "vested_amount": 0, "total_allocation": 0, "pre_claim_status": False,
                "vesting_end_date": None, "days_left_vesting": 0, "claim_transaction_hash": None
            }
        
        row = rows[0]
        total_allocation = float(row.get('total_allocation', 0))
        claimed_amount = float(row.get('claimed_amount', 0))
        is_claimed = bool(row.get('is_claimed', False))
        pre_claim_status = bool(row.get('pre_claim_status', False))
        claim_tx_hash = row.get('claim_transaction_hash')
        vesting_end_timestamp = row.get('vesting_end_date')
        
        days_left_vesting = 0
        vesting_end_date = None
        
        if vesting_end_timestamp:
            try:
                if isinstance(vesting_end_timestamp, str):
                    vesting_end_date = datetime.fromisoformat(vesting_end_timestamp.replace('Z', '+00:00'))
                elif isinstance(vesting_end_timestamp, (int, float)):
                    vesting_end_date = datetime.fromtimestamp(vesting_end_timestamp)
                
                if vesting_end_date:
                    days_left = (vesting_end_date - datetime.now()).days
                    days_left_vesting = max(0, days_left)
            except Exception as e:
                logging.warning(f"Error parsing vesting date: {e}")
        
        return {
            "wallet_address": wallet_address, "is_claimed": is_claimed, "claimed_amount": claimed_amount,
            "vested_amount": 0, "total_allocation": total_allocation, "pre_claim_status": pre_claim_status,
            "vesting_end_date": vesting_end_date, "days_left_vesting": days_left_vesting,
            "claim_transaction_hash": claim_tx_hash
        }
        
    except Exception as e:
        logging.error(f"Dune API error: {e}")
        return {
            "wallet_address": wallet_address, "is_claimed": False, "claimed_amount": 0,
            "vested_amount": 0, "total_allocation": 0, "pre_claim_status": False,
            "vesting_end_date": None, "days_left_vesting": 0, "claim_transaction_hash": None
        }

@api_router.get("/")
async def root():
    return {"message": "Era Airdrop Dashboard API", "status": "operational"}

@api_router.get("/airdrop/{wallet_address}", response_model=AirdropResponse)
async def get_airdrop_data(wallet_address: str):
    global query_count
    
    if not is_address(wallet_address):
        return AirdropResponse(success=False, data=None, message="Invalid Ethereum wallet address format")
    
    try:
        data_dict = await query_era_airdrop_data(wallet_address.lower())
        query_count += 1  # Simple counter
        return AirdropResponse(success=True, data=AirdropData(**data_dict), message="Data retrieved successfully")
    except Exception as e:
        return AirdropResponse(success=False, data=None, message=f"Failed to retrieve airdrop data: {str(e)}")

@api_router.get("/stats")
async def get_dashboard_stats():
    """Get simple dashboard statistics"""
    return {
        "total_queries": query_count,
        "recent_queries": 0,
        "status": "operational"
    }
# Serve the frontend HTML file
@app.get("/")
async def serve_frontend():
    return FileResponse('index.html')

# Include router and middleware
app.include_router(api_router)
# Include router and middleware
app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Era Airdrop Dashboard API started successfully!")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
