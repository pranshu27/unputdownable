from llm_guard.vault import Vault
from llm_guard.input_scanners import Anonymize, Secrets
from llm_guard.input_scanners.anonymize_helpers import BERT_BASE_NER_CONF
from llm_guard.output_scanners import Deanonymize


class LLMGuardService:

    def __init__(self):

        self.vault = Vault()

        self.anonymizer = Anonymize(
            self.vault,
            recognizer_conf=BERT_BASE_NER_CONF,
            language="en"
        )

        self.secrets_scanner = Secrets()

        self.deanonymizer = Deanonymize(self.vault)

    def sanitize_input(self, prompt: str):

        # Scan secrets first
        prompt, secrets_valid, secrets_risk = (
            self.secrets_scanner.scan(prompt)
        )

        # Then anonymize PII
        sanitized_prompt, pii_valid, pii_risk = (
            self.anonymizer.scan(prompt)
        )

        return {
            "sanitized_prompt": sanitized_prompt,
            "is_valid": secrets_valid and pii_valid,
            "risk_score": max(secrets_risk, pii_risk)
        }

    def restore_output(
        self,
        sanitized_prompt: str,
        llm_output: str
    ):

        restored_output, _, _ = self.deanonymizer.scan(
            sanitized_prompt,
            llm_output
        )

        return restored_output

guard_service = LLMGuardService()

## implement lazy loading if needed in future
# guard_service = None
# def get_guard_service():

#     global guard_service

#     if guard_service is None:
#         guard_service = LLMGuardService()

#     return guard_service



# # paste the below function inside any python module to use llm guard

# from llm_guard_service import guard_service
# def _sanitize_prompt(user_prompt: str) -> str:
#     """Sanitize every outbound LLM prompt before sending it to Azure OpenAI."""
#     result = guard_service.sanitize_input(user_prompt)
#     safe_prompt = result["sanitized_prompt"]
#     print("Original Prompt:", user_prompt)
#     print("Sanitized Prompt:", safe_prompt)
#     print("Is Valid:", result["is_valid"])
#     print("Risk Score:", result["risk_score"])
#     if not result.get("is_valid", True):
#         raise HTTPException(
#             status_code=400,
#             detail=(
#                 "Prompt guard blocked unsafe prompt "
#                 f"(risk_score={result.get('risk_score')})."
#             ),
#         )
#     return safe_prompt

# # now just call the function before passing any prompt to llm 

# user_prompt = "My email is xyz@abc.com"
# safe_prompt = guard_service.sanitize_input(user_prompt)

# #pass the safe prompt to LLM
