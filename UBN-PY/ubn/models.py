from pydantic import BaseModel, Field
from typing import Any, Optional, List

class ChatPresence(BaseModel):
    chatId: str
    level: int = Field(ge=1, le=3)
    data: dict[str, Any] = Field(default_factory=dict)

class Grant(BaseModel):
    granteePublicId: str
    level: int

class Webhook(BaseModel):
    id: str
    url: str
    events: List[str]

class SchemaContract(BaseModel):
    capability: str
    schemaVersion: str
    schema: dict[str, Any]
    updatedAt: int

class BotProfile(BaseModel):
    publicId: str
    name: str
    type: str
    bio: Optional[str] = None
    capabilities: List[str] = []
    features: List[str] = []
    verified: bool = False
    botUsername: Optional[str] = None
    defaultLevel: int = 1
    createdAt: int