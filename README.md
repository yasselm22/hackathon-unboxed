# hackathon-unboxed

UNBOXED Medical AI Agentic Hackathon: development of Mistral AI Agent for medical use in oncology services.

## Project description

The agent's aim is to aid radiologists in writing their reports based on patients' CT scans. The agent, specialized in reliable pulmonary detection, fetches from the DICOM database, thanks to the Orthanc API, the new series and studies as well as the previous ones and based on the previous reports written by the radiologist, generates a new report. The Agent also displays the images of interest where the nodules were found in order to show the nodules evolution.

The new report for each patient is structured as followed :

- Reason of study
- Clinical protocol
- Description of new findings
- Comparaison with the previous reports
- Conclusion on the evolution of the detected nodules and lesions

## How to run

```
python -r requirements.txt
python report-csv-to-json.py
cd backend
python -m uvicorn main:app --reload --port 8000

```

## Future features

As part of future features that we did not have time to fully implement :

- Allowing the radiologist to append and modify the generated reports so that the agent betters itself in later calls
- Implementing a RAG pipeline to the previous reports and current ones to suggest the next steps in the medical process

## Authors

EL HOUMA Mohamed
EL MOUKRI Yassmine
EL OUARDIGHI Nour
IQDARI Ikram
INSA Lyon
01/03/2026
