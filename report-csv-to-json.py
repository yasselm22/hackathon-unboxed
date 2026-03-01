import os
import io
import msoffcrypto
import pandas as pd
import dotenv
import json

dotenv.load_dotenv()

def convert_csv_to_json(file):
    """
    Reads reports from csv file and creates a json file for each one of them
    Returns None
    """

    if not os.path.isfile(file):
        raise FileNotFoundError(f"Audio file note found : {file}")
    
    password = os.getenv("EXCEL_PASSWORD")

    decrypted_file = io.BytesIO()
    
    with open(file, "rb") as f:
        office_file = msoffcrypto.OfficeFile(f)
        office_file.load_key(password=password)
        office_file.decrypt(decrypted_file)

    decrypted_file.seek(0)

    df = pd.read_excel(decrypted_file, engine = "openpyxl")

    report = {'patients' : {}}
    patients = []
    for i, row in df.iterrows():
        patient_id = row.get('PatientID')


        if (patient_id != None) and (patient_id not in patients) :
            patients.append(patient_id)
            patient = {'patient_ID' : patient_id, 'series' : []}
            
            series = []

            for j, row1 in df.iterrows():
                if row1.get('PatientID') == patient_id :
                    serie_type = row1.get('Série avec les masques de DICOM SEG\n')
                    access_id =  row1.get('AccessionNumber')
                    description = row1.get('Clinical information data (Pseudo reports)')
                    date = row1.get('Date')

                    series.append({
                        'serie_type' : serie_type,
                        'accession_id' : access_id,
                        'summary' : description,
                        'date' : date
                    })
                patient['series'] = series
            
            report['patients'][patient_id] = patient          
            
    with open('reports.json', "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"REPORT SAVED")
    

if __name__ == "__main__":
    file = "C:\\Users\\Admin\\Desktop\\Unboxed\\brouillon\\protected-clinical-data.xlsx"
    convert_csv_to_json(file)
    
