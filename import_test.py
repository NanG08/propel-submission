import sys, pathlib, importlib.util
repo_root = pathlib.Path(__file__).resolve().parent
sys.path.append(str(repo_root))
spec = importlib.util.find_spec('app.llm_client')
print('spec:', spec)
if spec:
    module = importlib.import_module('app.llm_client')
    print('imported', module)
