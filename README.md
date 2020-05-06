# dropbear

Oh they're real.

## Running it locally

1. Clone the repository:

```bash
git clone https://github.com:andycasey/dropbear
cd dropbear
```

2. Install a conda environment or virtual environment. For example:

```bash
conda env create -f environment.yml
conda activate dropbear

# or...

python -m venv env
source env/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

3. Make sure you have a NASA/ADS key stored on your computer (follow [these 'getting started' instructions](https://ads.readthedocs.io/en/latest/))

4. Start your searching:

```bash
dropbear "Casey, Andrew"
```
