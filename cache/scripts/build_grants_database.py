"""
Build comprehensive farmers.gov grants database

Manually curated grant data based on farmers.gov/working-with-us/program-deadlines
and detailed program pages. This provides comprehensive, structured grant information
for the voicebot RAG system.
"""

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = CACHE_DIR / "farmers_grants_comprehensive.json"


# Comprehensive grants database
GRANTS_DATABASE = {
    "EQIP": {
        "id": "EQIP",
        "name": "Environmental Quality Incentives Program",
        "acronym": "EQIP",
        "agency": "NRCS",
        "program_type": "conservation",
        "description": "EQIP provides financial and technical assistance to agricultural producers and forest landowners to plan and implement conservation practices that improve soil, water, plant, animal, air and related resources on agricultural land and non-industrial private forestland. Producers can receive cost-share payments and incentive payments to implement conservation practices.",
        "beneficiaries": ["farmer", "rancher", "forest_landowner", "agricultural_producer"],
        "deadline_info": {
            "type": "state_ranking_dates",
            "national_deadline": "2026-01-15",
            "description": "National batching deadline January 15, 2026 for first funding round. Applications accepted year-round, but producers should apply by their state's ranking dates for current cycle consideration.",
            "has_state_variations": True,
            "state_overrides": {}
        },
        "funding": {
            "cost_share_percentage": 75,
            "description": "Financial assistance through cost-share payments and incentive payments. Higher rates available for beginning farmers, socially disadvantaged, veteran, and limited resource producers.",
            "advance_payment_available": True,
            "underserved_premium": True
        },
        "eligibility": {
            "producer_types": ["farmer", "rancher", "forest_landowner", "agricultural_producer"],
            "underserved_categories": ["socially_disadvantaged", "beginning_farmer", "veteran", "limited_resource"],
            "land_ownership": "own_or_lease",
            "description": "Agricultural producers and forest landowners who are in compliance with highly erodible land and wetland conservation provisions. Must have an agricultural or forest operation.",
            "income_limits": False
        },
        "application": {
            "submission_method": ["in_person", "electronic"],
            "process": "Contact local NRCS office or USDA Service Center. Develop conservation plan with NRCS conservationist. Applications ranked competitively based on environmental benefits and state priorities.",
            "required_forms": [],
            "approval_process": "competitive_ranking"
        },
        "special_initiatives": [
            {
                "name": "EQIP Organic Initiative",
                "description": "Provides higher payment rates for organic producers or those transitioning to organic",
                "additional_funding": True
            },
            {
                "name": "High Tunnel Initiative",
                "description": "Cost-share for high tunnel systems to extend growing season",
                "additional_funding": True
            },
            {
                "name": "On-Farm Energy Initiative",
                "description": "Support for agricultural energy management and renewable energy systems",
                "additional_funding": True
            }
        ],
        "urls": {
            "main_page": "https://www.nrcs.usda.gov/programs-initiatives/eqip-environmental-quality-incentives-program",
            "state_ranking_dates": "https://www.nrcs.usda.gov/ranking-dates",
            "fact_sheet": "https://www.nrcs.usda.gov/programs-initiatives/eqip-environmental-quality-incentives-program"
        },
        "contact": "Local NRCS office through USDA Service Center Locator: https://www.farmers.gov/service-center-locator",
        "keywords": ["conservation", "soil health", "water quality", "wildlife habitat", "organic", "energy", "financial assistance", "cost-share"]
    },
    
    "CSP": {
        "id": "CSP",
        "name": "Conservation Stewardship Program",
        "acronym": "CSP",
        "agency": "NRCS",
        "program_type": "conservation",
        "description": "CSP helps agricultural producers maintain and improve their existing conservation systems and adopt additional conservation activities. It provides payments for conservation performance — the higher the performance, the higher the payment. CSP is available on tribal and private agricultural lands and non-industrial private forestland.",
        "beneficiaries": ["farmer", "rancher", "forest_landowner", "tribal_landowner"],
        "deadline_info": {
            "type": "state_ranking_dates",
            "national_deadline": "2026-01-15",
            "description": "National batching deadline January 15, 2026. Applications accepted year-round with state-specific ranking dates.",
            "has_state_variations": True,
            "state_overrides": {}
        },
        "funding": {
            "description": "Annual payments for installing new conservation activities and maintaining existing conservation practices. Five-year contracts. Higher payment rates for underserved producers.",
            "contract_length_years": 5,
            "payment_structure": "annual_per_acre",
            "underserved_premium": True
        },
        "eligibility": {
            "producer_types": ["farmer", "rancher", "forest_landowner", "tribal_landowner"],
            "underserved_categories": ["socially_disadvantaged", "beginning_farmer", "veteran", "limited_resource"],
            "land_ownership": "own_or_lease_or_tribal",
            "description": "Producers who meet stewardship threshold for at least two priority resource concerns. Must maintain existing conservation activities.",
            "income_limits": False
        },
        "application": {
            "submission_method": ["in_person", "electronic"],
            "process": "Contact local NRCS office. Complete conservation stewardship plan showing existing conservation and planned enhancements.",
            "approval_process": "competitive_ranking"
        },
        "urls": {
            "main_page": "https://www.nrcs.usda.gov/programs-initiatives/csp-conservation-stewardship-program",
            "state_ranking_dates": "https://www.nrcs.usda.gov/ranking-dates"
        },
        "contact": "Local NRCS office: https://www.farmers.gov/service-center-locator",
        "keywords": ["conservation", "stewardship", "existing conservation", "enhancement", "multi-year", "annual payments", "resource concerns"]
    },
    
    "ACEP": {
        "id": "ACEP",
        "name": "Agricultural Conservation Easement Program",
        "acronym": "ACEP",
        "agency": "NRCS",
        "program_type": "conservation",
        "description": "ACEP provides financial assistance to help conserve agricultural lands and wetlands and their related benefits. The program has two components: Agricultural Land Easements (ACEP-ALE) to protect working agricultural lands and Wetland Reserve Easements (ACEP-WRE) to restore and protect wetlands.",
        "beneficiaries": ["farmer", "rancher", "landowner", "tribal_entity", "conservation_organization"],
        "deadline_info": {
            "type": "state_ranking_dates_with_variations",
            "national_deadline": "2026-01-15",
            "description": "National batching deadline January 15, 2026 for most states. Some state variations exist (e.g., Alabama: January 25, 2026).",
            "has_state_variations": True,
            "state_overrides": {
                "AL": {"deadline": "2026-01-25", "notes": "Alabama has extended deadline"}
            }
        },
        "funding": {
            "description": "Federal share up to 50% of fair market value for agricultural land easements. Up to 75% for wetland reserve easements. 100% funding available for grasslands of special environmental significance.",
            "payment_structure": "easement_purchase",
            "components": ["ACEP-ALE", "ACEP-WRE"]
        },
        "eligibility": {
            "producer_types": ["landowner", "farmer", "rancher", "tribal_entity"],
            "land_ownership": "must_own",
            "description": "Landowners of private or tribal agricultural land. For ACEP-ALE: productive agricultural land or grassland. For ACEP-WRE: wetlands or land with wetland restoration potential.",
            "income_limits": False
        },
        "application": {
            "submission_method": ["in_person", "through_partner_organization"],
            "process": "ACEP-ALE: Apply through eligible partner entity (land trust, state/local government). ACEP-WRE: Apply directly to NRCS.",
            "approval_process": "competitive_ranking"
        },
        "urls": {
            "main_page": "https://www.nrcs.usda.gov/programs-initiatives/acep-agricultural-conservation-easement-program",
            "state_ranking_dates": "https://www.nrcs.usda.gov/ranking-dates"
        },
        "contact": "Local NRCS office: https://www.farmers.gov/service-center-locator",
        "keywords": ["easement", "wetlands", "agricultural land protection", "permanent protection", "grasslands", "working lands"]
    },
    
    "OFSCLP": {
        "id": "OFSCLP",
        "name": "On-Farm Stored Commodity Loss Program",
        "acronym": "OFSCLP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "OFSCLP provides assistance to producers who suffered losses of eligible harvested commodities (corn, grain sorghum, hay, oats, peanuts, pulse crops, rice, seed cotton, soybeans, wheat) while stored in on-farm structures in 2023 and/or 2024 due to a qualifying natural disaster event.",
        "beneficiaries": ["farmer", "agricultural_producer", "commodity_producer"],
        "deadline_info": {
            "type": "fixed_national",
            "national_deadline": "2026-01-23",
            "description": "Deadline to apply is January 23, 2026. Covers losses from 2023 and 2024 calendar years.",
            "has_state_variations": False,
            "loss_years": ["2023", "2024"]
        },
        "funding": {
            "description": "Payment equal to 75% of the loss value based on NAP price or higher of market price at time of loss.",
            "payment_rate": "75% of loss",
            "maximum_payment": "$125,000 per person or entity per year"
        },
        "eligibility": {
            "producer_types": ["farmer", "agricultural_producer"],
            "eligible_commodities": ["corn", "grain sorghum", "hay", "oats", "peanuts", "pulse crops", "rice", "seed cotton", "soybeans", "wheat"],
            "qualifying_events": ["drought", "earthquake", "excessive wind", "flood", "freeze", "hurricane", "tornado", "typhoon", "wildfire"],
            "description": "Producers who had eligible commodities stored in on-farm structures and suffered losses due to qualifying natural disaster events in 2023 or 2024.",
            "income_limits": True,
            "agi_limit": "$900,000"
        },
        "application": {
            "submission_method": ["in_person", "electronic", "email", "fax"],
            "required_forms": [
                {"form_id": "FSA-878", "name": "OFSCLP Application"},
                {"form_id": "AD-2047", "name": "Customer Data Worksheet"},
                {"form_id": "CCC-902", "name": "Farm Operating Plan"},
                {"form_id": "CCC-901", "name": "Member Information"},
                {"form_id": "SF-3881", "name": "ACH Vendor/Miscellaneous Payment Enrollment"},
                {"form_id": "AD-1026", "name": "Highly Erodible Land Conservation and Wetland Conservation Certification"}
            ],
            "process": "Submit application to local FSA county office. Provide documentation of stored commodity, storage structure, and disaster event.",
            "approval_process": "verification_and_payment"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/ofsclp",
            "forms": "https://www.fsa.usda.gov/ofsclp"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["disaster", "commodity loss", "on-farm storage", "natural disaster", "grain", "soybeans", "corn", "hay", "stored crops"]
    },
    
    "MLP": {
        "id": "MLP",
        "name": "Milk Loss Program",
        "acronym": "MLP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "MLP provides payments to eligible dairy operations for milk that was dumped or removed without compensation from the commercial milk market because of a qualifying weather event in 2023 and/or 2024.",
        "beneficiaries": ["dairy_operator", "dairy_farmer"],
        "deadline_info": {
            "type": "fixed_national",
            "national_deadline": "2026-01-23",
            "description": "Deadline to apply is January 23, 2026. Covers milk losses from 2023 and 2024.",
            "has_state_variations": False,
            "loss_years": ["2023", "2024"]
        },
        "funding": {
            "description": "Payment calculated based on base period milk production per cow, number of milking cows, number of days milk was dumped, and applicable milk price.",
            "payment_calculation": "Base milk production × cows × days dumped × milk price",
            "maximum_funding": "$1,650,000 total program (prorated if exceeded)"
        },
        "eligibility": {
            "producer_types": ["dairy_operator"],
            "qualifying_events": ["drought", "earthquake", "excessive wind", "flood", "freeze", "hurricane", "tornado", "typhoon", "wildfire"],
            "description": "Dairy operations that dumped milk due to a qualifying weather event in 2023 or 2024. Must provide milk marketing statements and documentation.",
            "income_limits": True,
            "agi_limit": "$900,000"
        },
        "application": {
            "submission_method": ["in_person", "electronic", "email", "fax"],
            "required_forms": [
                {"form_id": "FSA-376", "name": "MLP Application"},
                {"form_id": "AD-1026", "name": "HELC/WC Certification"}
            ],
            "supporting_documents": ["Milk marketing statements", "Documentation of weather event", "Records of dumped milk"],
            "process": "Submit application to local FSA county office with milk marketing statements and disaster documentation.",
            "approval_process": "verification_and_payment"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/mlp"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["dairy", "milk loss", "disaster", "dumped milk", "weather event", "natural disaster"]
    },
    
    "FSCSC": {
        "id": "FSCSC",
        "name": "Food Safety Certification for Specialty Crops Program",
        "acronym": "FSCSC",
        "agency": "USDA",
        "program_type": "specialty",
        "description": "FSCSC provides financial assistance for specialty crop operations that incur eligible on-farm food safety program expenses related to obtaining or renewing a food safety certification. This helps offset costs to comply with regulatory requirements and market-driven food safety certification requirements.",
        "beneficiaries": ["specialty_crop_producer", "farmer"],
        "deadline_info": {
            "type": "annual_enrollment",
            "national_deadline": "2026-01-31",
            "description": "Application period for calendar year 2025 is January 1, 2025 through January 31, 2026.",
            "enrollment_period": "January 1, 2025 - January 31, 2026",
            "has_state_variations": False
        },
        "funding": {
            "description": "Reimbursement for eligible expenses related to obtaining or renewing food safety certification.",
            "cost_share_percentage": 50,
            "maximum_payment": "$250 per scope/audit",
            "eligible_expenses": ["Certification/audit costs", "Training", "Documentation"]
        },
        "eligibility": {
            "producer_types": ["specialty_crop_producer"],
            "description": "Specialty crop operations (fruits, vegetables, tree nuts, nursery crops, floriculture) that incur eligible food safety certification expenses.",
            "eligible_crops": ["fruits", "vegetables", "tree nuts", "nursery crops", "floriculture"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["electronic", "in_person"],
            "process": "Submit application with documentation of eligible expenses and food safety certification.",
            "approval_process": "reimbursement"
        },
        "urls": {
            "main_page": "https://www.farmers.gov/node/29355"
        },
        "contact": "Local USDA Service Center: https://www.farmers.gov/service-center-locator",
        "keywords": ["specialty crops", "food safety", "certification", "audit", "reimbursement", "fruits", "vegetables"]
    },
    
    "SDRP": {
        "id": "SDRP",
        "name": "Supplemental Disaster Relief Program",
        "acronym": "SDRP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "SDRP provides assistance to producers for necessary expenses due to losses of revenue, quality or production of crops due to weather-related events in 2023 and 2024. Stage 1 covers indemnified losses (insured through Federal Crop Insurance or NAP). Stage 2 covers non-indemnified losses including shallow losses, uncovered/uninsured losses, and quality losses.",
        "beneficiaries": ["farmer", "agricultural_producer", "crop_producer"],
        "deadline_info": {
            "type": "fixed_national",
            "national_deadline": "2026-04-30",
            "description": "Deadline to apply for Stage 1 and Stage 2 is April 30, 2026. Covers losses from 2023 and 2024 weather events.",
            "has_state_variations": False,
            "loss_years": ["2023", "2024"],
            "stages": ["Stage 1: Indemnified losses", "Stage 2: Non-indemnified, shallow, uncovered, and quality losses"]
        },
        "funding": {
            "description": "Stage 1: Uses Federal Crop Insurance or NAP data to calculate payments. Stage 2: Covers additional loss types not fully covered by insurance.",
            "payment_basis": "Crop insurance/NAP data for Stage 1, additional documentation for Stage 2"
        },
        "eligibility": {
            "producer_types": ["farmer", "agricultural_producer"],
            "description": "Producers who suffered crop losses due to weather-related events in 2023 or 2024. Stage 1 for insured losses, Stage 2 for uninsured/under-insured losses.",
            "qualifying_events": ["weather-related disasters in 2023-2024"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person", "electronic"],
            "process": "Stage 1 producers: FSA will use existing crop insurance/NAP data. Stage 2 producers: Submit additional loss documentation.",
            "approval_process": "verification_and_payment"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/resources/programs/supplemental-disaster-relief-program-sdrp"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["disaster relief", "crop loss", "weather", "insurance", "quality loss", "shallow loss", "supplemental", "2023", "2024"]
    },
    
    # Ongoing Programs
    
    "ECP": {
        "id": "ECP",
        "name": "Emergency Conservation Program",
        "acronym": "ECP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "ECP provides funding and technical assistance for farmers and ranchers to restore farmland damaged by natural disasters and for emergency water conservation measures in severe droughts.",
        "beneficiaries": ["farmer", "rancher"],
        "deadline_info": {
            "type": "disaster_triggered",
            "description": "Applications accepted following disaster declarations. Contact local FSA office after disaster event. Signup periods vary by county and disaster.",
            "has_state_variations": True
        },
        "funding": {
            "cost_share_percentage": 75,
            "description": "Cost-share assistance to restore farmland damaged by natural disasters or for emergency water conservation."
        },
        "eligibility": {
            "producer_types": ["farmer", "rancher"],
            "description": "Farmers and ranchers whose land has been damaged by a natural disaster or who need emergency water conservation in severe drought.",
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Contact local FSA office after disaster event. Submit application within specified timeframe after disaster.",
            "approval_process": "disaster_verification"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/resources/programs/emergency-conservation-program-ecp"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["emergency", "conservation", "disaster", "farmland restoration", "drought", "water conservation"]
    },
    
    "EFRP": {
        "id": "EFRP",
        "name": "Emergency Forest Restoration Program",
        "acronym": "EFRP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "EFRP provides funding to restore privately owned forests damaged by natural disasters.",
        "beneficiaries": ["forest_landowner"],
        "deadline_info": {
            "type": "disaster_triggered",
            "description": "Applications accepted following disaster declarations affecting forestland. Contact local FSA office after disaster event.",
            "has_state_variations": True
        },
        "funding": {
            "cost_share_percentage": 75,
            "description": "Cost-share payments for restoration activities on private forestland damaged by natural disasters."
        },
        "eligibility": {
            "producer_types": ["forest_landowner"],
            "description": "Private forestland owners whose land was damaged by natural disaster.",
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Contact local FSA office after disaster event affecting forestland.",
            "approval_process": "disaster_verification"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/programs-and-services/disaster-assistance-program/emergency-forest-restoration"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["forest", "forestland", "disaster", "restoration", "trees", "emergency"]
    },
    
    "NAP": {
        "id": "NAP",
        "name": "Noninsured Crop Disaster Assistance Program",
        "acronym": "NAP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "NAP provides financial assistance to producers of non-insurable crops to protect against natural disasters that result in lower yields or crop losses, or prevent crop planting.",
        "beneficiaries": ["farmer", "agricultural_producer", "specialty_crop_producer"],
        "deadline_info": {
            "type": "ongoing_with_crop_deadlines",
            "description": "Application deadlines vary by crop and county. Generally, must apply before crop planting deadline. Contact local FSA office for crop-specific deadlines.",
            "has_state_variations": True
        },
        "funding": {
            "description": "Catastrophic (CAT) coverage: Pays 55% of average market price for crop losses exceeding 50%. Buy-up coverage available for higher levels.",
            "coverage_levels": ["CAT coverage (free except service fee)", "Buy-up coverage (additional premium)"]
        },
        "eligibility": {
            "producer_types": ["farmer", "agricultural_producer"],
            "description": "Producers of non-insurable crops (specialty crops, aquaculture, floriculture, etc.). Must apply before crop-specific deadline.",
            "eligible_crops": ["specialty crops", "mushrooms", "floriculture", "ornamental nursery", "aquaculture", "turf grass sod", "many others"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Apply before crop planting deadline at local FSA office. Pay service fee for CAT coverage or premium for buy-up.",
            "approval_process": "enrollment"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/resources/programs/noninsured-crop-disaster-assistance-related-information"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["non-insurable crops", "disaster assistance", "specialty crops", "crop insurance", "catastrophic coverage", "aquaculture"]
    },
    
    "TAP": {
        "id": "TAP",
        "name": "Tree Assistance Program",
        "acronym": "TAP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "TAP provides financial cost-share assistance to qualifying orchardists and nursery tree growers to replant or, where applicable, rehabilitate eligible trees, bushes, and vines lost by natural disasters.",
        "beneficiaries": ["orchardist", "nursery_grower", "farmer"],
        "deadline_info": {
            "type": "disaster_triggered",
            "description": "Must report loss within 15 days of when loss is apparent or 15 days of disaster event end, whichever is later. Application deadlines vary by disaster.",
            "has_state_variations": True
        },
        "funding": {
            "cost_share_percentage": 65,
            "description": "Cost-share for replanting or rehabilitating eligible trees, bushes, and vines. 75% for beginning and socially disadvantaged farmers.",
            "underserved_rate": 75
        },
        "eligibility": {
            "producer_types": ["orchardist", "nursery_grower"],
            "description": "Orchardists and nursery tree growers who lost eligible trees, bushes, or vines due to natural disaster. Must have suffered at least 15% mortality or damage.",
            "minimum_loss": "15%",
            "eligible_plants": ["fruit trees", "nut trees", "nursery trees", "bushes", "vines"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Report loss to FSA within 15 days. Submit application at local FSA office.",
            "approval_process": "loss_verification"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/programs-and-services/disaster-assistance-program/tree-assistance-program"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["trees", "orchard", "nursery", "replanting", "disaster", "fruit trees", "nut trees", "rehabilitation"]
    },
    
    "ELAP": {
        "id": "ELAP",
        "name": "Emergency Assistance for Livestock, Honeybees, and Farm-Raised Fish Program",
        "acronym": "ELAP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "ELAP provides financial assistance to eligible producers of livestock, honeybees and farm-raised fish for losses due to disease, certain adverse weather events or loss conditions, including blizzards and wildfires.",
        "beneficiaries": ["livestock_producer", "beekeeper", "aquaculture_producer"],
        "deadline_info": {
            "type": "disaster_triggered",
            "description": "Must report loss within 30 days of when loss is apparent or 30 days of disaster end, whichever is later. Application deadline within 30 days of end of program year.",
            "has_state_variations": True,
            "notice_period": "30 days"
        },
        "funding": {
            "description": "Payments for eligible losses of livestock, honeybees, farm-raised fish due to eligible adverse weather or loss conditions."
        },
        "eligibility": {
            "producer_types": ["livestock_producer", "beekeeper", "aquaculture_producer"],
            "description": "Producers who suffered livestock, honeybee, or farm-raised fish losses due to eligible adverse weather or loss conditions.",
            "eligible_animals": ["livestock", "honeybees", "farm-raised fish"],
            "qualifying_events": ["blizzard", "wildfire", "disease", "adverse weather"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Report loss within 30 days to FSA. Submit application at local FSA office with documentation.",
            "approval_process": "loss_verification"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/resources/programs/emergency-assistance-livestock-honeybees-farm-raised-fish-elap"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["livestock", "honeybees", "fish", "aquaculture", "disaster", "disease", "wildfire", "blizzard", "emergency"]
    },
    
    "LIP": {
        "id": "LIP",
        "name": "Livestock Indemnity Program",
        "acronym": "LIP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "LIP provides benefits to livestock owners and some contract growers for livestock deaths in excess of normal mortality caused by eligible loss conditions, including eligible adverse weather, eligible disease and attacks by animals reintroduced into the wild by the federal government or protected by federal law.",
        "beneficiaries": ["livestock_producer", "livestock_owner", "contract_grower"],
        "deadline_info": {
            "type": "disaster_triggered",
            "description": "Must report loss within 30 days of when loss is first apparent. Application deadline within 30 days of fiscal year end for losses in that year.",
            "has_state_variations": True,
            "notice_period": "30 days"
        },
        "funding": {
            "description": "Payments based on 75% of average fair market value for livestock deaths exceeding normal mortality."
        },
        "eligibility": {
            "producer_types": ["livestock_owner", "contract_grower"],
            "description": "Livestock owners and contract growers who suffered livestock deaths exceeding normal mortality due to eligible loss conditions.",
            "qualifying_events": ["adverse weather", "eligible disease", "attacks by protected animals (wolves, avian predators)"],
            "eligible_animals": ["cattle", "sheep", "goats", "horses", "poultry", "swine", "other livestock"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Report loss within 30 days to FSA. Submit application with documentation of deaths and cause.",
            "approval_process": "loss_verification"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/programs-and-services/disaster-assistance-program/livestock-indemnity"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["livestock", "livestock deaths", "disaster", "mortality", "adverse weather", "disease", "wolves", "predators"]
    },
    
    "LFP": {
        "id": "LFP",
        "name": "Livestock Forage Disaster Program",
        "acronym": "LFP",
        "agency": "FSA",
        "program_type": "disaster",
        "description": "LFP provides payments to eligible livestock owners and contract growers who have covered livestock and produce grazed forage crop acreage that has suffered a loss of grazed forage due to a qualifying drought during the normal grazing period for the county.",
        "beneficiaries": ["livestock_producer", "livestock_owner", "contract_grower"],
        "deadline_info": {
            "type": "disaster_triggered",
            "description": "Must report loss within 30 days after grazing season end for county. Application deadline within 30 days of fiscal year end.",
            "has_state_variations": True,
            "notice_period": "30 days after grazing season"
        },
        "funding": {
            "description": "Monthly payment rates based on drought severity (D2, D3, D4 on U.S. Drought Monitor) and number of covered livestock."
        },
        "eligibility": {
            "producer_types": ["livestock_owner", "contract_grower"],
            "description": "Livestock owners/growers who suffered forage loss due to qualifying drought during normal grazing period.",
            "qualifying_events": ["drought (D2, D3, D4 severity)", "fire on federally managed land"],
            "eligible_animals": ["cattle", "sheep", "goats", "livestock"],
            "income_limits": True
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Report loss within 30 days after grazing season end. Submit application at local FSA office.",
            "approval_process": "drought_verification"
        },
        "urls": {
            "main_page": "https://www.fsa.usda.gov/resources/programs/livestock-forage-disaster-program-lfp"
        },
        "contact": "Local FSA County Office: https://www.farmers.gov/service-center-locator",
        "keywords": ["livestock", "forage", "grazing", "drought", "pasture", "disaster", "D2", "D3", "D4", "drought monitor"]
    },
    
    "OTI": {
        "id": "OTI",
        "name": "Organic Transition Initiative",
        "acronym": "OTI",
        "agency": "USDA",
        "program_type": "specialty",
        "description": "OTI provides support for farmers transitioning to organic farming through various USDA programs including EQIP Organic Initiative, organic crop insurance, organic certification cost share, and organic market development assistance.",
        "beneficiaries": ["farmer", "rancher", "transitioning_to_organic", "organic_producer"],
        "deadline_info": {
            "type": "ongoing",
            "description": "Contact local USDA Service Center for information. Deadlines vary by specific program component (EQIP, certification cost share, etc.).",
            "has_state_variations": True
        },
        "funding": {
            "description": "Financial assistance through multiple USDA programs including EQIP Organic Initiative, organic certification cost share, and transition support.",
            "higher_rates": True
        },
        "eligibility": {
            "producer_types": ["farmer", "rancher", "forest_landowner"],
            "description": "Farmers and ranchers transitioning to organic or certified organic. Must develop organic system plan aligned with NRCS conservation plan.",
            "certification_status": ["transitioning", "certified_organic"]
        },
        "application": {
            "submission_method": ["in_person"],
            "process": "Contact local USDA Service Center or NRCS office to learn about available organic transition support programs.",
            "approval_process": "varies_by_program"
        },
        "urls": {
            "main_page": "https://www.farmers.gov/your-business/organic/organic-transition-initiative/assistance"
        },
        "contact": "Local USDA Service Center: https://www.farmers.gov/service-center-locator",
        "keywords": ["organic", "transition", "organic certification", "EQIP organic", "organic farming", "certification cost share"]
    }
}


def build_grants_database():
    """Build comprehensive grants database JSON file"""
    print("🏗️  Building comprehensive grants database...\n")
    
    # Add metadata
    output = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "source": "farmers.gov/working-with-us/program-deadlines + individual program pages",
            "total_grants": len(GRANTS_DATABASE),
            "data_quality": "manually_curated",
            "last_updated": "2026-01-06",
            "coverage": "Federal USDA programs with deadlines and ongoing programs"
        },
        "grants": list(GRANTS_DATABASE.values())
    }
    
    # Save to JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Created comprehensive grants database:")
    print(f"   📁 File: {OUTPUT_FILE}")
    print(f"   📊 Total grants: {len(GRANTS_DATABASE)}")
    print(f"   🏛️  Agencies: NRCS, FSA, USDA")
    print(f"   📅 With deadlines: {sum(1 for g in GRANTS_DATABASE.values() if g['deadline_info'].get('national_deadline'))}")
    print(f"   🔄 Ongoing programs: {sum(1 for g in GRANTS_DATABASE.values() if g['deadline_info']['type'] in ['ongoing', 'disaster_triggered', 'ongoing_with_crop_deadlines'])}")
    
    # Print program categories
    program_types = {}
    for grant in GRANTS_DATABASE.values():
        ptype = grant['program_type']
        program_types[ptype] = program_types.get(ptype, 0) + 1
    
    print(f"\n   📋 By type:")
    for ptype, count in sorted(program_types.items()):
        print(f"      • {ptype}: {count}")
    
    print("\n✨ Database ready for RAG indexing!")


if __name__ == "__main__":
    build_grants_database()
