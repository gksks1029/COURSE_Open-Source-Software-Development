"""Build two Iris SVC models with the exact serving image's dependencies."""
import hashlib
import json
from pathlib import Path

import joblib
import sklearn
from sklearn.datasets import load_iris
from sklearn.svm import SVC

iris = load_iris()
metadata = {"sklearn_version": sklearn.__version__, "models": {}}
for version, regularization in [("v1", 1.0), ("v2", 10.0)]:
    model = SVC(C=regularization, gamma="scale").fit(iris.data, iris.target)
    directory = Path("/models") / version
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model.joblib"
    joblib.dump(model, path)
    metadata["models"][version] = {
        "C": regularization,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "example_predictions": model.predict([[6.8, 2.8, 4.8, 1.4], [6.0, 3.4, 4.5, 1.6]]).tolist(),
    }
assert metadata["models"]["v1"]["sha256"] != metadata["models"]["v2"]["sha256"]
Path("/models/metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(json.dumps(metadata, indent=2), flush=True)
