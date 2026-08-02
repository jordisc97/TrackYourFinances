from app.config import get_settings
from app.providers.base import BankProvider
from app.providers.enable_banking import EnableBankingProvider
from app.providers.gocardless import GoCardlessProvider

PROVIDER_GOCARDLESS = "gocardless"
PROVIDER_ENABLE_BANKING = "enable_banking"


def get_bank_provider() -> BankProvider:
    provider_name = get_settings().bank_provider.strip().lower()
    if provider_name == PROVIDER_ENABLE_BANKING:
        return EnableBankingProvider()
    return GoCardlessProvider()
