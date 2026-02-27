import os, base64
os.makedirs("C:/medigate_dev", exist_ok=True)
data = base64.b64decode(open("C:/medigate_dev/_payload.b64","r").read())
open("C:/medigate_dev/test_crawl.py","wb").write(data)
print("written:", len(data), "bytes")
