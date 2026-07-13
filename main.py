import requests
 
def decode_vin(vin, model_year=None):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}"
    params = {"format": "json"}
    if model_year:
        params["modelyear"] = model_year
 
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["Results"][0]  # flat dict of all decoded fields
 
 
if __name__ == "__main__":
    data = decode_vin("5UXWX7C5*BA", model_year=2011)
 
    # Print only the populated fields
    for key, value in data.items():
        if value not in ("", None):
            print(f"{key}: {value}")
