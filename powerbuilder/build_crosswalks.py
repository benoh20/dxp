# save as build_crosswalks.py in your project root
from dotenv import load_dotenv
load_dotenv()
from chat.utils.crosswalk_builder import build_crosswalk

# House districts
house_districts = [
    ('04', '0401'),  # AZ-01
    ('04', '0402'),  # AZ-02
    ('04', '0406'),  # AZ-06
    ('32', '3201'),  # NV-01
    ('32', '3203'),  # NV-03
    ('32', '3204'),  # NV-04
    ('26', '2607'),  # MI-07
    ('26', '2608'),  # MI-08
    ('26', '2610'),  # MI-10
    ('39', '3901'),  # OH-01
    ('39', '3909'),  # OH-09
    ('39', '3913'),  # OH-13
    ('33', '3301'),  # NH-01
    ('33', '3302'),  # NH-02
    ('42', '4207'),  # PA-07
    ('42', '4208'),  # PA-08
    ('08', '0808'),  # CO-08
    ('55', '5503'),  # WI-03
]

# Statewide races (senate/governor use 'statewide' as district_id)
statewide = [
    ('04', 'statewide'),  # AZ
    ('13', 'statewide'),  # GA
    ('26', 'statewide'),  # MI
    ('33', 'statewide'),  # NH
    ('32', 'statewide'),  # NV
    ('55', 'statewide'),  # WI
]

all_districts = house_districts + statewide

for fips, district in all_districts:
    print(f"Building crosswalk for state {fips}, district {district}...")
    try:
        build_crosswalk(state_fips=fips, district_id=district)
        print(f"  ✅ Done")
    except Exception as e:
        print(f"  ❌ Failed: {e}")

print("All done.")