import importlib, inspect
module = importlib.import_module("fawkes.fuzzers.file_fuzzer")
print("Classes in module:")
for name, obj in vars(module).items():
    if inspect.isclass(obj):
        print("  ", name)

