import os
from datetime import datetime, timezone
from typing import Optional, List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "librarydb"
    mongo_collection: str = "loans"
    host: str = "0.0.0.0"
    port: int = 8050

    class Config:
        env_file = ".env"


settings = Settings()

app = FastAPI(title="library-loans-api")

client = AsyncIOMotorClient(settings.mongo_uri)
db = client[settings.mongo_db]
collection = db[settings.mongo_collection]


class LoanIn(BaseModel):
    reader_name: str
    book_title: str
    returned: bool = False


class LoanUpdate(BaseModel):
    reader_name: Optional[str] = None
    book_title: Optional[str] = None
    returned: Optional[bool] = None


class LoanOut(BaseModel):
    id: str
    reader_name: str
    book_title: str
    returned: bool
    created_at: datetime
    updated_at: datetime


def doc_to_out(doc) -> LoanOut:
    return LoanOut(
        id=str(doc["_id"]),
        reader_name=doc["reader_name"],
        book_title=doc["book_title"],
        returned=doc["returned"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def parse_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid id format")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/loans", response_model=LoanOut, status_code=201)
async def create_loan(payload: LoanIn):
    now = datetime.now(timezone.utc)
    doc = payload.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc_to_out(doc)


@app.get("/api/v1/loans", response_model=List[LoanOut])
async def list_loans(
    returned: Optional[bool] = Query(default=None),
    book_title: Optional[str] = Query(default=None),
):
    query = {}
    if returned is not None:
        query["returned"] = returned
    if book_title:
        query["book_title"] = book_title
    cursor = collection.find(query)
    return [doc_to_out(doc) async for doc in cursor]


@app.get("/api/v1/loans/{loan_id}", response_model=LoanOut)
async def get_loan(loan_id: str):
    oid = parse_object_id(loan_id)
    doc = await collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    return doc_to_out(doc)


@app.patch("/api/v1/loans/{loan_id}", response_model=LoanOut)
async def update_loan(loan_id: str, payload: LoanUpdate):
    oid = parse_object_id(loan_id)
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_data["updated_at"] = datetime.now(timezone.utc)
    result = await collection.find_one_and_update(
        {"_id": oid}, {"$set": update_data}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Loan not found")
    return doc_to_out(result)


@app.delete("/api/v1/loans/{loan_id}", status_code=204)
async def delete_loan(loan_id: str):
    oid = parse_object_id(loan_id)
    result = await collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Loan not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
