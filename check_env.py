import os

def check_env_var(var_name):
    return "Set" if os.environ.get(var_name) else "Not set"

print(f"SUPABASE_URL: {check_env_var('SUPABASE_URL')}")
print(f"SUPABASE_SERVICE_ROLE_KEY: {check_env_var('SUPABASE_SERVICE_ROLE_KEY')}")
print(f"SUPABASE_ANON_KEY: {check_env_var('SUPABASE_ANON_KEY')}")
