import os
import json
from mistralai import Mistral

# ==========================
# 1️⃣ Charger les données JSON
# ==========================

with open("nodule_result.json", "r", encoding="utf-8") as f:
    nodule_data = json.load(f)

# ==========================
# 2️⃣ Construire le prompt
# ==========================
# {
#   "patient_id": "12345",
#   "exam_date": "2026-02-15",
#   "nodule": {
#     "location": "Right upper lobe",
#     "volume_mm3": 523.4,
#     "max_diameter_mm": 11.2,
#     "mean_density_HU": -120,
#     "growth_percent": 18.4
#   },
#   "previous_report": "Right upper lobe nodule measuring 9 mm, stable."
# }


prompt = f"""
You are a senior thoracic radiologist.

Here are the structured CT findings:

Patient ID: {nodule_data['patient_id']}
Exam Date: {nodule_data['exam_date']}

Nodule Characteristics:
- Location: {nodule_data['nodule']['location']}
- Volume: {nodule_data['nodule']['volume_mm3']} mm3
- Maximum diameter: {nodule_data['nodule']['max_diameter_mm']} mm
- Mean density: {nodule_data['nodule']['mean_density_HU']} HU
- Growth since previous exam: {nodule_data['nodule']['growth_percent']} %

Previous report:
{nodule_data['previous_report']}

Write a structured radiology report with the following sections:
- Indication
- Technique
- Findings
- Comparison
- Impression

Use professional medical language.
Do NOT invent values.
"""

# ==========================
# 3️⃣ Connexion à Mistral
# ==========================

client = Mistral(api_key=os.getenv("API_KEY"))

# ==========================
# 4️⃣ Appel au modèle
# ==========================

response = client.chat.complete(
    model="mistral-small-latest",  # ou mistral-medium selon votre plan
    messages=[
        {"role": "system", "content": "You are a precise and factual medical report generator."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.2  # faible température = moins d'hallucination
)

# ==========================
# 5️⃣ Afficher le rapport généré
# ==========================

generated_report = response.choices[0].message.content
print("\n===== GENERATED REPORT =====\n")
print(generated_report)


