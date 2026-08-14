def get_license_name(sku_part_number: str) -> str:
    """Get license name from sku_part_number"""
    # https://learn.microsoft.com/en-us/entra/identity/users/licensing-service-plan-reference
    corresponding_license = {
        "FLOW_FREE": "Microsoft Power Automate Free",
        "O365_BUSINESS_ESSENTIALS": "Microsoft 365 Business Basic",
        "O365_BUSINESS_PREMIUM": "Microsoft 365 Business Standard",
        "PROJECT_PLAN3_DEPT": "Project Plan 3 (for Department)",
        "SPB": "Microsoft 365 Business Premium",
        "POWERAPPS_DEV": "Microsoft PowerApps for Developer",
        "PROJECTPROFESSIONAL": "Project Plan 3",
    }
    return corresponding_license.get(sku_part_number, sku_part_number)
