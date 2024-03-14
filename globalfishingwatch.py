import aiohttp
import asyncio

async def connect_globalfishingwatch():
    url = "https://gateway.api.globalfishingwatch.org"
    api_key = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtpZEtleSJ9.eyJkYXRhIjp7Im5hbWUiOiJGSVNISU5HIiwidXNlcklkIjozMjY0MiwiYXBwbGljYXRpb25OYW1lIjoiRklTSElORyIsImlkIjoxMzQwLCJ0eXBlIjoidXNlci1hcHBsaWNhdGlvbiJ9LCJpYXQiOjE3MTAyMDcwOTcsImV4cCI6MjAyNTU2NzA5NywiYXVkIjoiZ2Z3IiwiaXNzIjoiZ2Z3In0.dDkyet_WgzRMAACpIz4KiXEFdtOj86CPM0gkBGV8qc6h_Uw4K5hruRSN3cODbFS2OUneFnibhKCLJzFjOnn2QhthsC5hyfKBwMVew0f4VmtvFpPeGhBEtmAermJCt1TfBL2xZnqppLVihU9mYrNMk0POaBFC7Bj-15DT3EYlIiG5VBnaPeKtzbQ3Z7q7sAMUt4xJRYCgESZGJB3gAcImu0oSCr8jGiM9qVVnz0tz0lO6LSKt0c8DRM3fcQ0uopqkilIC8Cp0bcl-pyb-Y5uK9wjspelrkb1o5KORZsv1eHiTvGc7Cf14PHXGR14v4OQh4X7ty4dIp1nMcwEbrESq9RgEL1GIVx_-8w4ne7BGNxghlKk-Z4Kmk0imndz-jWibr_9A-xdnopvcITFCODk-0AekqjQmvCeAndN8_xKjJsfckuIq4kbHool7GUOcnD0T1RIkwofom3ZfgH3L4Ag5reGzFR7DHXEmZfqyXJ2ev2dtvZfXOMyuid0uyJo-aL7_"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                print(data)
            else:
                print(f"Failed to retrieve data: {response.status}")

if __name__ == "__main__":
    asyncio.run(connect_globalfishingwatch())