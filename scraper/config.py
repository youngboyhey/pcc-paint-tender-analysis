import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://chclxcbmdzgdozldufzs.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

PCC_BASE_URL = "https://web.pcc.gov.tw"
PCC_SEARCH_URL = f"{PCC_BASE_URL}/prkms/tender/common/bulletion/readBulletion"
PCC_AWARD_DETAIL_URL = f"{PCC_BASE_URL}/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail"

SEARCH_KEYWORD = "建築物及道路零星油漆長約工作"
YEAR_START = 105
YEAR_END = 115
