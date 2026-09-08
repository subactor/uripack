"""One JSON request on stdin, one JSON response on stdout."""
import json
import sys

URI = "demo://services/python/count"
request = json.load(sys.stdin)
print(json.dumps({"uri": URI, "count": len(request["items"])}))
