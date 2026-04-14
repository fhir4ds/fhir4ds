---
id: notebooks
title: Notebooks
---

# Interactive Notebooks

Try FHIR4DS in your browser using Google Colab. These notebooks demonstrate the core capabilities of the toolkit without requiring any local installation.

## Get Started

| Notebook | Description | Open in Colab |
|----------|-------------|---------------|
| **FHIRPath** | Core FHIRPath R4 parsing and evaluation. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/fhirpath.ipynb) |
| **CQL** | CQL-to-SQL translation and population evaluation. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/cql.ipynb) |
| **ViewDefinition** | SQL-on-FHIR v2 ViewDefinition generator. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/viewdef.ipynb) |
| **DQM** | Measure evaluation and clinical audit trails. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/dqm.ipynb) |

Each notebook begins with `pip install fhir4ds-v2` and imports from `fhir4ds`. No other setup is required.

## Local Usage

To run these notebooks locally, install the package and launch Jupyter:

```bash
pip install "fhir4ds-v2[measures]"
jupyter notebook docs/notebooks/
```

Or clone the repository for the latest development version:

```bash
git clone https://github.com/joelmontavon/fhir4ds-v2.git
cd fhir4ds
pip install -e ".[measures]"
jupyter notebook docs/notebooks/
```
