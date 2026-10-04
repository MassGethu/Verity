import os
from pydantic import BaseModel, ConfigDict
from django.core.management.base import BaseCommand
from recruitment.services.providers import generate
from unittest.mock import patch

class HealthResponse(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message: str
class Command(BaseCommand):
    help='Make one small structured-output request to each configured provider; provider account billing may apply.'
    def handle(self,*args,**kwargs):
        for provider,key,other in [('gemini','GEMINI_API_KEY','GROQ_API_KEY'),('groq','GROQ_API_KEY','GEMINI_API_KEY')]:
            if not os.getenv(key): self.stdout.write(f'{provider}: not configured (no request sent)');continue
            with patch.dict(os.environ,{other:''}):
                try:
                    data,meta=generate(HealthResponse,'Return message exactly as: Verity structured output works.',{})
                    self.stdout.write(self.style.SUCCESS(f'{provider}: structured response valid ({meta["model"]})'))
                except Exception as exc:self.stderr.write(f'{provider}: {exc}')
