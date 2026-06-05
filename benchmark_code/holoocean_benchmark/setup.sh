#!/usr/bin/env bash
set -e

ENV_NAME="benchmark_holoocean"

# 1. Create conda env
conda create -y -n "$ENV_NAME" python=3.10
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

# 2. System deps (Linux)
sudo apt-get install -y build-essential

# 3. Clone repo (requires Epic/GitHub link)
git clone git@github.com:byu-holoocean/HoloOcean.git holoocean_src

# 4. Install Python client from source
cd holoocean_src/client
pip install .
cd ../..

# 5. Download Ocean world binaries
python -c "import holoocean; holoocean.install('Ocean')"

echo "Done! Activate with: conda activate $ENV_NAME"