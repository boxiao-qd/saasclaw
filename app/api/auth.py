from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from app.dao.user_dao import UserDAO
from app.auth.jwt_utils import hash_password, verify_password, create_access_token
from app.db.database import get_session_factory

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 32:
            raise ValueError("用户名长度必须在 3-32 字符之间")
        if not v.replace("_", "").isalnum():
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码长度至少 6 位")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    employee_id: int


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    dao = UserDAO(get_session_factory())
    existing = await dao.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    hashed = hash_password(req.password)
    user = await dao.create(username=req.username, hashed_password=hashed)
    if user is None:
        # concurrent registration: unique constraint triggered between check and insert
        raise HTTPException(status_code=409, detail="用户名已存在")
    token = create_access_token(user.employee_id)
    return TokenResponse(access_token=token, username=req.username, employee_id=user.employee_id)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    dao = UserDAO(get_session_factory())
    user = await dao.get_by_username(req.username)
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.employee_id)
    return TokenResponse(access_token=token, username=user.username, employee_id=user.employee_id)
