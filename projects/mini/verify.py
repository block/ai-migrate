import sys
import subprocess

filename = sys.argv[1]
out = (
    subprocess.run(["python", filename], check=True, capture_output=True)
    .stdout.decode()
    .strip()
)
assert out == "fizzbuzz\nfizzbuzz\nfizzbuzz"
