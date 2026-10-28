---
id: notebooks
title: Notebooks
---

# Interactive Notebooks

Try FHIR4DS in your browser using Google Colab. These notebooks demonstrate the core capabilities of the toolkit without requiring any local installation.

## Get Started

| Notebook | Description | Open in Colab |
|----------|-------------|---------------|
| **FHIRPath** | Core FHIRPath R4 parsing and evaluation. | [![Open In Colab](https://img.shields.io/badge/Open%20In%20Colab-F9AB00?logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/fhirpath.ipynb) |
| **CQL** | CQL-to-SQL translation and population evaluation. | [![Open In Colab](https://img.shields.io/badge/Open%20In%20Colab-F9AB00?logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/cql.ipynb) |
| **ViewDefinition** | SQL-on-FHIR v2 ViewDefinition generator. | [![Open In Colab](https://img.shields.io/badge/Open%20In%20Colab-F9AB00?logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/viewdef.ipynb) |
| **DQM** | Measure evaluation and clinical audit trails. | [![Open In Colab](https://img.shields.io/badge/Open%20In%20Colab-F9AB00?logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/dqm.ipynb) |
| **OMOP** | FHIR R4 to OMOP CDM v5.5 — person, encounters, concept maps and the cross-resource medications union. | [![Open In Colab](https://img.shields.io/badge/Open%20In%20Colab-F9AB00?logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/fhir4ds/fhir4ds/blob/main/docs/notebooks/omop-mapping.ipynb) |

Each notebook begins with `pip install fhir4ds-v2==0.0.19` and imports from
`fhir4ds`. No other setup is required. The OMOP notebook additionally
downloads its cohort from
[Hugging Face](https://huggingface.co/datasets/fhir4ds/omop-demo) (no token
needed).

New to the mapping? [FHIR → OMOP](/docs/examples/fhir-to-omop)
builds `person` and the concept map by hand first.

## Local Usage

To run these notebooks locally, install the package and launch Jupyter:

```bash
pip install "fhir4ds-v2[measures]==0.0.19"
jupyter notebook docs/notebooks/
```

Or clone the repository for the latest development version:

```bash
git clone https://github.com/fhir4ds/fhir4ds.git
cd fhir4ds
pip install -e ".[measures]"
jupyter notebook docs/notebooks/
```
