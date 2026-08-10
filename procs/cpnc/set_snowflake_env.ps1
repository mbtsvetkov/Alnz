# Sets the SNOWFLAKE_* env vars for this PowerShell session (dbt_yaml_generator's
# --fill-types-from-snowflake / --source snowflake paths, and any future procs\cpnc\* tool).
#
# MUST be dot-sourced, not just run, or the env vars only exist inside this script's
# own child scope and vanish the moment it exits:
#   . .\procs\cpnc\set_snowflake_env.ps1
#
# Password is prompted securely (masked input) every time -- never stored on disk,
# safe to run on a shared screen. Requires a cached MFA token (see seed_mfa.py) for
# a silent connect; adjust ACCOUNT/USER/ROLE/WAREHOUSE/DATABASE/SCHEMA below to match
# your own login and target.

$env:SNOWFLAKE_ACCOUNT   = "dq41125.west-europe.privatelink"
$env:SNOWFLAKE_USER      = "TSVETM"
$env:SNOWFLAKE_ROLE      = "DEV_DEVELOPER_DBT"
$env:SNOWFLAKE_WAREHOUSE = "DEV_WAREHOUSE_DEVELOPER_DBT"
$env:SNOWFLAKE_DATABASE  = "DBAREA_COMMON"
$env:SNOWFLAKE_SCHEMA    = "DBT_TSVETM"

$sec = Read-Host "Snowflake password" -AsSecureString
$env:SNOWFLAKE_PASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [System.Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($sec)
)

Write-Host "SNOWFLAKE_* env vars set for this session."
