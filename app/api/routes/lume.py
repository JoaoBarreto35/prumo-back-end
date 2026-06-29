from fastapi import APIRouter, Depends, HTTPException
from google import genai

from app.core.settings import settings
from app.dependencies import get_current_user
from app.models.entities import User
from app.schemas import LumeRequest, LumeResponse

router = APIRouter(prefix="/lume", tags=["Lume"])


@router.post("/message", response_model=LumeResponse)
def send_message(data: LumeRequest, _: User = Depends(get_current_user)):
    try:
        client = genai.Client(api_key=settings.gemini_api_key_value)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=(
                "Você é o Lume, assistente financeiro do Prumo. "
                "Seja direto, amigável, não julgue e não invente valores. "
                f"Mensagem do usuário: {data.message}"
            ),
        )
        return LumeResponse(answer=response.text or "Não consegui produzir uma resposta.")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="O Lume está temporariamente indisponível.") from exc
