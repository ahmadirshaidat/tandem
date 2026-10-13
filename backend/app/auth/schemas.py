from pydantic import BaseModel, EmailStr, Field, field_validator


class EmailInput(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class Login(EmailInput):
    password: str = Field(min_length=1, max_length=128)


class Register(EmailInput):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class ResetPassword(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    name: str
    email: str
