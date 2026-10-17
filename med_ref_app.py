import streamlit as st
import requests
import math
import re
import html
from datetime import datetime
from itertools import combinations
from typing import Dict, Any, Optional, List, Tuple

st.set_page_config(
    page_title="Clinical Indication-Driven Dosing & Interaction System",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .warning-box { background-color: #fff3cd; border-left: 6px solid #ffecb5; padding: 15px; border-radius: 5px; color: #664d03; margin-bottom: 20px; }
    .boxed-warning { background-color: #f8d7da; border-left: 6px solid #dc3545; padding: 15px; border-radius: 5px; color: #842029; margin-bottom: 20px; }
    .interaction-high { background-color: #f8d7da; border-left: 6px solid #dc3545; padding: 12px 15px; border-radius: 5px; color: #842029; margin-bottom: 12px; }
    .interaction-moderate { background-color: #fff3cd; border-left: 6px solid #ffc107; padding: 12px 15px; border-radius: 5px; color: #664d03; margin-bottom: 12px; }
    .interaction-clear { background-color: #d1e7dd; border-left: 6px solid #198754; padding: 12px 15px; border-radius: 5px; color: #0f5132; margin-bottom: 12px; }
    .counseling-box { background-color: #e0f2fe; border-left: 6px solid #0284c7; padding: 15px; border-radius: 5px; color: #075985; margin-top: 15px; }
    </style>
""", unsafe_allow_html=True)

class DrugDataClient:
    OPENFDA_URL = "https://api.fda.gov/drug/label.json"
    RXNORM_URL = "https://rxnav.nlm.nih.gov/REST"

    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def resolve_rxnorm_ingredient(drug_name: str) -> Dict[str, str]:
        clean_name = drug_name.strip()
        result = {"input": clean_name, "rxcui": "N/A", "normalized_name": clean_name.lower()}
        try:
            resp = requests.get(
                f"{DrugDataClient.RXNORM_URL}/approximateTerm.json",
                params={"term": clean_name, "maxEntries": 1},
                timeout=6
            )
            if resp.status_code == 200:
                candidates = resp.json().get("approximateGroup", {}).get("candidate", [])
                if candidates:
                    rxcui = candidates[0].get("rxcui")
                    result["rxcui"] = rxcui
                    prop_resp = requests.get(f"{DrugDataClient.RXNORM_URL}/rxcui/{rxcui}/properties.json", timeout=6)
                    if prop_resp.status_code == 200:
                        prop_name = prop_resp.json().get("properties", {}).get("name")
                        if prop_name:
                            result["normalized_name"] = prop_name.lower()
        except requests.RequestException:
            pass
        return result

    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def fetch_drug_label(drug_name: str) -> Optional[Dict[str, Any]]:
        clean_name = drug_name.strip().lower()
        if not clean_name:
            return None

        queries = [
            f'openfda.generic_name:"{clean_name}"',
            f'openfda.brand_name:"{clean_name}"',
            f'active_ingredient:"{clean_name}"'
        ]

        for query in queries:
            try:
                params = {"search": query, "limit": 1}
                response = requests.get(DrugDataClient.OPENFDA_URL, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "results" in data and len(data["results"]) > 0:
                        return DrugDataClient._parse_label_data(data["results"][0])
            except requests.RequestException:
                continue
        return None

    @staticmethod
    def _extract_field(raw_data: Dict[str, Any], field_name: str, default: str = "Not specified in official FDA label.") -> str:
        content = raw_data.get(field_name)
        if isinstance(content, list) and len(content) > 0:
            return "\n\n".join(content)
        return default

    @staticmethod
    def _parse_label_data(result: Dict[str, Any]) -> Dict[str, Any]:
        openfda = result.get("openfda", {})
        
        def get_openfda_list(key: str) -> List[str]:
            items = openfda.get(key, [])
            return list(set(items)) if items else []

        generic_list = get_openfda_list("generic_name")
        brand_list = get_openfda_list("brand_name")
        class_list = get_openfda_list("pharm_class_epc") + get_openfda_list("pharm_class_FM")

        return {
            "brand_name": ", ".join(brand_list) if brand_list else "N/A",
            "generic_name": ", ".join(generic_list) if generic_list else "N/A",
            "generic_list": [g.lower() for g in generic_list],
            "brand_list": [b.lower() for b in brand_list],
            "class_list": [c.lower() for c in class_list],
            "manufacturer": ", ".join(get_openfda_list("manufacturer_name")) or "N/A",
            "route": ", ".join(get_openfda_list("route")) or "N/A",
            "pharm_class": ", ".join(get_openfda_list("pharm_class_epc")) or "N/A",
            "boxed_warning": DrugDataClient._extract_field(result, "boxed_warning", default=""),
            "indications": DrugDataClient._extract_field(result, "indications_and_usage"),
            "dosage_and_admin": DrugDataClient._extract_field(result, "dosage_and_administration"),
            "contraindications": DrugDataClient._extract_field(result, "contraindications"),
            "warnings": DrugDataClient._extract_field(result, "warnings_and_cautions", 
                                                     DrugDataClient._extract_field(result, "warnings")),
            "interactions": DrugDataClient._extract_field(result, "drug_interactions"),
            "adverse_reactions": DrugDataClient._extract_field(result, "adverse_reactions"),
            "specific_populations": DrugDataClient._extract_field(result, "use_in_specific_populations"),
            "overdosage": DrugDataClient._extract_field(result, "overdosage"),
            "mechanism": DrugDataClient._extract_field(result, "mechanism_of_action"),
        }

class PairwiseInteractionEngine:
    CLASS_KEYWORD_MAP = {
        "nsaid": ["ibuprofen", "naproxen", "diclofenac", "celecoxib", "meloxicam", "ketorolac", "indomethacin", "aspirin"],
        "anticoagulant": ["warfarin", "apixaban", "rivaroxaban", "dabigatran", "edoxaban", "heparin", "enoxaparin"],
        "antiplatelet": ["aspirin", "clopidogrel", "prasugrel", "ticagrelor"],
        "ace inhibitor": ["lisinopril", "enalapril", "ramipril", "benazepril", "captopril", "perindopril"],
        "arb": ["losartan", "valsartan", "irbesartan", "olmesartan", "candesartan", "telmisartan"],
        "potassium-sparing diuretic": ["spironolactone", "eplerenone", "amiloride", "triamterene"],
        "loop diuretic": ["furosemide", "bumetanide", "torsemide"],
        "macrolide": ["clarithromycin", "erythromycin", "azithromycin"],
        "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin"],
        "statin": ["simvastatin", "atorvastatin", "rosuvastatin", "pravastatin", "lovastatin"],
        "ssri": ["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram"],
        "snri": ["venlafaxine", "duloxetine", "desvenlafaxine"],
        "maoi": ["phenelzine", "tranylcypromine", "selegiline", "linezolid"],
        "opioid": ["morphine", "oxycodone", "hydrocodone", "fentanyl", "tramadol", "codeine", "methadone"],
        "benzodiazepine": ["alprazolam", "lorazepam", "diazepam", "clonazepam", "midazolam"],
        "nitrate": ["nitroglycerin", "isosorbide mononitrate", "isosorbide dinitrate"],
        "pde5 inhibitor": ["sildenafil", "tadalafil", "vardenafil"],
        "cyp3a4 inhibitor": ["clarithromycin", "erythromycin", "ketoconazole", "itraconazole", "ritonavir", "diltiazem", "verapamil"],
        "ppi": ["omeprazole", "pantoprazole", "lansoprazole", "esomeprazole", "rabeprazole"],
        "h2ra": ["famotidine", "ranitidine", "cimetidine", "nizatidine"],
    }

    CURATED_CLINICAL_RULES = [
        {
            "group_a": ["warfarin", "apixaban", "rivaroxaban", "dabigatran"],
            "group_b": ["ibuprofen", "naproxen", "diclofenac", "ketorolac", "meloxicam", "aspirin", "ciprofloxacin", "clarithromycin", "sulfamethoxazole", "trimethoprim"],
            "severity": "Major / High Risk",
            "summary": "Increased risk of serious bleeding due to pharmacokinetic enzyme inhibition or mucosal injury."
        },
        {
            "group_a": ["sildenafil", "tadalafil", "vardenafil"],
            "group_b": ["nitroglycerin", "isosorbide mononitrate", "isosorbide dinitrate"],
            "severity": "Contraindicated",
            "summary": "Synergistic vasodilation via nitric oxide-cGMP causes profound, life-threatening hypotension."
        },
        {
            "group_a": ["simvastatin", "lovastatin", "atorvastatin"],
            "group_b": ["clarithromycin", "erythromycin", "itraconazole", "ketoconazole", "gemfibrozil"],
            "severity": "Contraindicated / Major",
            "summary": "Potent CYP3A4/OATP1B1 inhibition markedly elevates statin concentrations, risking rhabdomyolysis."
        },
        {
            "group_a": ["lisinopril", "enalapril", "ramipril", "losartan", "valsartan"],
            "group_b": ["spironolactone", "eplerenone", "amiloride", "triamterene", "potassium chloride", "trimethoprim"],
            "severity": "Major / Monitor Closely",
            "summary": "Additive hyperkalemic effects. Concurrent use elevates risk of severe hyperkalemia."
        },
        {
            "group_a": ["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "venlafaxine", "duloxetine"],
            "group_b": ["phenelzine", "tranylcypromine", "selegiline", "linezolid", "tramadol", "sumatriptan", "metoclopramide"],
            "severity": "Major / Serotonin Syndrome Risk",
            "summary": "Concurrent serotonergic agents significantly elevate risk of fatal serotonin syndrome or EPS."
        },
        {
            "group_a": ["morphine", "oxycodone", "hydrocodone", "fentanyl", "methadone", "tramadol"],
            "group_b": ["alprazolam", "lorazepam", "diazepam", "clonazepam", "zolpidem", "promethazine"],
            "severity": "Major (Boxed Warning)",
            "summary": "Concomitant use may result in profound sedation, respiratory depression, coma, and death."
        },
        {
            "group_a": ["methotrexate"],
            "group_b": ["amoxicillin", "penicillin", "ampicillin", "piperacillin", "ibuprofen", "naproxen", "trimethoprim", "sulfamethoxazole", "omeprazole", "pantoprazole"],
            "severity": "Major",
            "summary": "Reduced renal tubular clearance or additive folate antagonism causes severe methotrexate toxicity."
        },
        {
            "group_a": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "domperidone"],
            "group_b": ["theophylline", "tizanidine", "amiodarone", "ondansetron", "clarithromycin", "erythromycin"],
            "severity": "Major / Contraindicated",
            "summary": "QTc prolongation risk or profound enzyme inhibition resulting in severe toxicity or arrhythmias."
        }
    ]

    @classmethod
    def get_search_terms_for_drug(cls, drug_profile: Dict[str, Any]) -> List[str]:
        terms = set()
        norm_name = drug_profile["rxnorm"]["normalized_name"]
        terms.add(norm_name)
        
        first_token = norm_name.split()[0]
        if len(first_token) > 3:
            terms.add(first_token)

        if drug_profile.get("fda_data"):
            for g in drug_profile["fda_data"].get("generic_list", []):
                terms.add(g)
                if len(g.split()[0]) > 3:
                    terms.add(g.split()[0])
            for b in drug_profile["fda_data"].get("brand_list", []):
                if len(b) > 3:
                    terms.add(b)

        for class_name, members in cls.CLASS_KEYWORD_MAP.items():
            if any(m in norm_name or norm_name in m for m in members):
                terms.add(class_name)

        return sorted(list(terms), key=len, reverse=True)

    @staticmethod
    def extract_matching_sentences(text: str, search_terms: List[str], max_snippets: int = 3) -> List[str]:
        if not text or "Not specified" in text:
            return []

        sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
        matches = []

        for sentence in sentences:
            clean_s = sentence.strip()
            if len(clean_s) < 20 or len(clean_s) > 650:
                continue
            for term in search_terms:
                pattern = rf'\b{re.escape(term)}s?\b'
                if re.search(pattern, clean_s, flags=re.IGNORECASE):
                    highlighted = re.sub(
                        pattern,
                        lambda m: f"**{m.group(0)}**",
                        clean_s,
                        flags=re.IGNORECASE
                    )
                    if highlighted not in matches:
                        matches.append(highlighted)
                    break
            if len(matches) >= max_snippets:
                break

        return matches

    @classmethod
    def evaluate_pair(cls, drug_a: Dict[str, Any], drug_b: Dict[str, Any]) -> Dict[str, Any]:
        name_a = drug_a["rxnorm"]["normalized_name"]
        name_b = drug_b["rxnorm"]["normalized_name"]

        findings = []
        severity = "None Detected"
        severity_rank = 0

        for rule in cls.CURATED_CLINICAL_RULES:
            a_in_1 = any(x in name_a for x in rule["group_a"]) and any(y in name_b for y in rule["group_b"])
            a_in_2 = any(x in name_b for x in rule["group_a"]) and any(y in name_a for y in rule["group_b"])
            if a_in_1 or a_in_2:
                severity = rule["severity"]
                severity_rank = 2
                findings.append({
                    "source": "Clinical Pharmacotherapy Rule",
                    "excerpt": f"**{rule['severity']}:** {rule['summary']}"
                })

        terms_a = cls.get_search_terms_for_drug(drug_a)
        terms_b = cls.get_search_terms_for_drug(drug_b)

        if drug_a.get("fda_data"):
            fda_a = drug_a["fda_data"]
            contra_hits_a = cls.extract_matching_sentences(fda_a["contraindications"], terms_b, max_snippets=2)
            inter_hits_a = cls.extract_matching_sentences(fda_a["interactions"], terms_b, max_snippets=3)
            warn_hits_a = cls.extract_matching_sentences(fda_a["warnings"], terms_b, max_snippets=2)

            if contra_hits_a:
                severity_rank = max(severity_rank, 2)
                if severity == "None Detected":
                    severity = "Contraindicated / Major"
                for h in contra_hits_a:
                    findings.append({"source": f"{name_a.title()} FDA Label (Contraindications)", "excerpt": h})

            for h in inter_hits_a + warn_hits_a:
                if any(k in h.lower() for k in ["contraindicat", "avoid concomitant", "life-threatening", "fatal", "serious bleeding", "rhabdomyolysis"]):
                    severity_rank = max(severity_rank, 2)
                    if severity == "None Detected":
                        severity = "Major Interaction"
                else:
                    severity_rank = max(severity_rank, 1)
                    if severity == "None Detected":
                        severity = "Moderate / Precaution"
                findings.append({"source": f"{name_a.title()} FDA Label (Interactions/Warnings)", "excerpt": h})

        if drug_b.get("fda_data"):
            fda_b = drug_b["fda_data"]
            contra_hits_b = cls.extract_matching_sentences(fda_b["contraindications"], terms_a, max_snippets=2)
            inter_hits_b = cls.extract_matching_sentences(fda_b["interactions"], terms_a, max_snippets=3)
            warn_hits_b = cls.extract_matching_sentences(fda_b["warnings"], terms_a, max_snippets=2)

            if contra_hits_b:
                severity_rank = max(severity_rank, 2)
                if severity == "None Detected":
                    severity = "Contraindicated / Major"
                for h in contra_hits_b:
                    findings.append({"source": f"{name_b.title()} FDA Label (Contraindications)", "excerpt": h})

            for h in inter_hits_b + warn_hits_b:
                if any(k in h.lower() for k in ["contraindicat", "avoid concomitant", "life-threatening", "fatal", "serious bleeding", "rhabdomyolysis"]):
                    severity_rank = max(severity_rank, 2)
                    if severity == "None Detected":
                        severity = "Major Interaction"
                else:
                    severity_rank = max(severity_rank, 1)
                    if severity == "None Detected":
                        severity = "Moderate / Precaution"
                findings.append({"source": f"{name_b.title()} FDA Label (Interactions/Warnings)", "excerpt": h})

        return {
            "pair": f"{name_a.title()} + {name_b.title()}",
            "drug_a": name_a.title(),
            "drug_b": name_b.title(),
            "severity": severity,
            "severity_rank": severity_rank,
            "findings": findings
        }

class PediatricWeightValidator:
    REFERENCE_GROWTH_TABLE: List[Tuple[float, float, float, float]] = [
        (0.0,   2.5,  3.4,  4.4), (1.0,   3.4,  4.4,  5.7), (2.0,   4.3,  5.4,  6.9), (3.0,   5.0,  6.2,  7.8),
        (6.0,   6.2,  7.6,  9.5), (9.0,   7.0,  8.6, 10.7), (12.0,  7.6,  9.4, 11.6), (18.0,  8.6, 10.7, 13.3),
        (24.0,  9.6, 12.0, 15.0), (36.0, 11.2, 14.1, 17.8), (48.0, 12.6, 16.2, 20.8), (60.0, 14.1, 18.3, 24.2),
        (72.0, 15.8, 20.7, 28.0), (84.0, 17.5, 23.2, 32.5), (96.0, 19.3, 25.8, 37.5), (108.0, 21.2, 28.8, 43.2),
        (120.0, 23.3, 32.2, 49.5), (144.0, 28.5, 40.8, 63.5), (168.0, 36.0, 51.0, 77.0), (192.0, 43.0, 58.5, 86.0),
        (216.0, 47.5, 63.5, 92.0),
    ]

    @classmethod
    def get_interpolated_bounds(cls, age_months: float) -> Tuple[float, float, float]:
        table = cls.REFERENCE_GROWTH_TABLE
        if age_months <= table[0][0]:
            return table[0][1], table[0][2], table[0][3]
        if age_months >= table[-1][0]:
            return table[-1][1], table[-1][2], table[-1][3]

        for i in range(len(table) - 1):
            m0, p3_0, p50_0, p97_0 = table[i]
            m1, p3_1, p50_1, p97_1 = table[i + 1]
            if m0 <= age_months <= m1:
                ratio = (age_months - m0) / (m1 - m0) if m1 > m0 else 0.0
                p3 = p3_0 + ratio * (p3_1 - p3_0)
                p50 = p50_0 + ratio * (p50_1 - p50_0)
                p97 = p97_0 + ratio * (p97_1 - p97_0)
                return p3, p50, p97

        return table[-1][1], table[-1][2], table[-1][3]

    @classmethod
    def validate_pediatric_weight(cls, age_value: float, age_unit: str, weight_kg: float) -> Dict[str, Any]:
        age_months = age_value * 12.0 if age_unit == "Years" else age_value
        p3, p50, p97 = cls.get_interpolated_bounds(age_months)

        extreme_low = p3 * 0.55
        extreme_high = p97 * 1.65

        status = "normal"
        messages = []

        weight_if_entered_in_lbs = weight_kg / 2.20462
        weight_if_entered_in_kg = weight_kg * 2.20462

        if weight_kg < extreme_low:
            status = "critical"
            unit_hint = f" Possible Unit Error Detected: Converting {weight_kg:.1f} from lbs yields {weight_if_entered_in_kg:.1f} kg (normal range)." if (p3 <= weight_if_entered_in_kg <= p97) else ""
            messages.append(f"🛑 CLINICALLY IMPLAUSIBLE LOW WEIGHT: Entered weight ({weight_kg:.2f} kg) is critically below the 3rd percentile ({p3:.1f} kg).{unit_hint}")
        elif weight_kg > extreme_high:
            status = "critical"
            unit_hint = f" Possible lb/kg Unit Reversal: {weight_kg:.1f} lbs equals {weight_if_entered_in_lbs:.1f} kg (normal range). Dosing on {weight_kg:.1f} kg instead would cause a 2.2-fold overdose!" if (p3 <= weight_if_entered_in_lbs <= p97) else ""
            messages.append(f"🛑 CLINICALLY IMPLAUSIBLE HIGH WEIGHT: Entered weight ({weight_kg:.2f} kg) drastically exceeds the 97th percentile ({p97:.1f} kg).{unit_hint}")
        elif weight_kg < p3:
            status = "warning"
            messages.append(f"⚠️ Low Weight-for-Age (< 3rd Percentile): Entered weight ({weight_kg:.2f} kg) is below the 3rd percentile ({p3:.1f} kg).")
        elif weight_kg > p97:
            status = "warning"
            messages.append(f"⚠️ High Weight-for-Age (> 97th Percentile): Entered weight ({weight_kg:.2f} kg) exceeds the 97th percentile ({p97:.1f} kg).")

        pct_of_median = (weight_kg / p50) * 100.0 if p50 > 0 else 0.0

        return {
            "age_display": f"{age_value:g} {age_unit.lower()}",
            "age_months": age_months,
            "p3_kg": p3,
            "p50_kg": p50,
            "p97_kg": p97,
            "pct_of_median": pct_of_median,
            "status": status,
            "messages": messages
        }

class IndicationDosingEngine:
    GUIDELINES = {
        "Amoxicillin": {
            "indications": {
                "Acute Otitis Media (Standard Dose)": {"dose_mg_kg_day": 45.0, "freq": 2, "max_daily": 1750.0},
                "Acute Otitis Media (High Dose / Resistant S. pneumoniae)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_daily": 4000.0},
                "Streptococcal Pharyngitis (Strep Throat)": {"dose_mg_kg_day": 50.0, "freq": 2, "max_daily": 1000.0},
                "Acute Bacterial Rhinosinusitis": {"dose_mg_kg_day": 45.0, "freq": 2, "max_daily": 2000.0},
                "Community-Acquired Pneumonia (First-Line High Dose)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_daily": 4000.0}
            },
            "forms": {
                "Oral Suspension 400 mg / 5 mL": {"type": "liquid", "conc_mg": 400, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Chewable Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"},
                "Oral Capsule 500 mg": {"type": "solid", "strength_mg": 500, "unit": "capsule"}
            },
            "counseling": [
                "Can be taken with or without food. Taking with food may decrease stomach upset.",
                "Complete the entire course of therapy even if feeling better.",
                "Shake suspension well before each use. Store suspension in refrigerator; discard after 14 days.",
                "May cause mild diarrhea. Notify clinician if diarrhea is severe or bloody."
            ]
        },
        "Amoxicillin-Clavulanate (Augmentin)": {
            "indications": {
                "Acute Otitis Media (High Dose 14:1 / Amox Failure)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_daily": 4000.0},
                "Acute Bacterial Rhinosinusitis (High Dose)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_daily": 4000.0},
                "Bite Wounds (Human / Animal)": {"dose_mg_kg_day": 40.0, "freq": 3, "max_daily": 1500.0}
            },
            "forms": {
                "Oral Suspension 600 mg / 5 mL (Augmentin ES 14:1)": {"type": "liquid", "conc_mg": 600, "conc_ml": 5},
                "Oral Suspension 400 mg / 5 mL (7:1)": {"type": "liquid", "conc_mg": 400, "conc_ml": 5},
                "Oral Tablet 875/125 mg": {"type": "solid", "strength_mg": 875, "unit": "tablet"}
            },
            "counseling": [
                "Take with meals or snacks to maximize absorption and minimize stomach upset.",
                "Refrigerate the suspension and shake well before each use. Discard after 10 days.",
                "Higher risk of diarrhea compared to amoxicillin alone. Contact clinician if severe.",
                "Do not substitute two 250 mg tablets for one 500 mg tablet (clavulanate toxicity risk)."
            ]
        },
        "Cefdinir (Omnicef)": {
            "indications": {
                "Acute Otitis Media (Penicillin Allergy)": {"dose_mg_kg_day": 14.0, "freq": 2, "max_daily": 600.0},
                "Acute Bacterial Sinusitis": {"dose_mg_kg_day": 14.0, "freq": 2, "max_daily": 600.0},
                "Streptococcal Pharyngitis (Penicillin Allergy)": {"dose_mg_kg_day": 14.0, "freq": 1, "max_daily": 600.0}
            },
            "forms": {
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Capsule 300 mg": {"type": "solid", "strength_mg": 300, "unit": "capsule"}
            },
            "counseling": [
                "Do not take antacids containing magnesium/aluminum or iron supplements within 2 hours of taking cefdinir.",
                "May cause stools to temporarily turn a harmless red/rust color (especially if taking iron).",
                "Store suspension at room temperature. Do not refrigerate. Discard after 10 days."
            ]
        },
        "Cephalexin (Keflex)": {
            "indications": {
                "Skin & Soft Tissue Infection (Cellulitis/Impetigo)": {"dose_mg_kg_day": 50.0, "freq": 3, "max_daily": 2000.0},
                "Streptococcal Pharyngitis (Penicillin Allergy)": {"dose_mg_kg_day": 40.0, "freq": 2, "max_daily": 1000.0},
                "Urinary Tract Infection (Mild/Uncomplicated)": {"dose_mg_kg_day": 50.0, "freq": 4, "max_daily": 2000.0}
            },
            "forms": {
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Capsule 250 mg": {"type": "solid", "strength_mg": 250, "unit": "capsule"},
                "Oral Capsule 500 mg": {"type": "solid", "strength_mg": 500, "unit": "capsule"}
            },
            "counseling": [
                "Can be taken with or without food. Take with food if stomach upset occurs.",
                "Shake suspension well before using. Keep refrigerated and discard after 14 days.",
                "Complete the full course even if symptoms disappear early."
            ]
        },
        "Clindamycin (Cleocin)": {
            "indications": {
                "Skin & Soft Tissue Infection (Community MRSA Suspected)": {"dose_mg_kg_day": 30.0, "freq": 3, "max_daily": 1800.0},
                "Severe Bone/Joint Infection (Osteomyelitis)": {"dose_mg_kg_day": 40.0, "freq": 3, "max_daily": 2700.0},
                "Odontogenic / Dental Infection": {"dose_mg_kg_day": 20.0, "freq": 3, "max_daily": 1800.0}
            },
            "forms": {
                "Oral Solution 75 mg / 5 mL": {"type": "liquid", "conc_mg": 75, "conc_ml": 5},
                "Oral Capsule 150 mg": {"type": "solid", "strength_mg": 150, "unit": "capsule"},
                "Oral Capsule 300 mg": {"type": "solid", "strength_mg": 300, "unit": "capsule"}
            },
            "counseling": [
                "Take with a full glass of water to prevent esophageal irritation.",
                "Can be taken with or without food.",
                "🛑 Contact clinician immediately if you develop severe, watery, or bloody diarrhea (risk of C. difficile infection)."
            ]
        },
        "Sulfamethoxazole-Trimethoprim (Bactrim)": {
            "indications": {
                "Urinary Tract Infection (Dosed on TMP Component)": {"dose_mg_kg_day": 8.0, "freq": 2, "max_daily": 320.0},
                "Community MRSA Skin Infection (Dosed on TMP Component)": {"dose_mg_kg_day": 10.0, "freq": 2, "max_daily": 320.0}
            },
            "forms": {
                "Oral Suspension (40 mg TMP / 200 mg SMX per 5 mL)": {"type": "liquid", "conc_mg": 40, "conc_ml": 5},
                "Single Strength Tablet (80 mg TMP / 400 mg SMX)": {"type": "solid", "strength_mg": 80, "unit": "tablet"},
                "Double Strength Tablet (160 mg TMP / 800 mg SMX)": {"type": "solid", "strength_mg": 160, "unit": "tablet"}
            },
            "counseling": [
                "Drink plenty of water or fluids while taking this medication to prevent kidney stones.",
                "Avoid prolonged exposure to sunlight or tanning beds; use sunscreen (high risk of photosensitivity).",
                "Contact clinician if a severe skin rash, blistering, or peeling occurs."
            ]
        },
        "Azithromycin (Zithromax)": {
            "indications": {
                "Community-Acquired Pneumonia / Pertussis (Day 1)": {"dose_mg_kg_day": 10.0, "freq": 1, "max_daily": 500.0},
                "Community-Acquired Pneumonia / Pertussis (Days 2-5)": {"dose_mg_kg_day": 5.0, "freq": 1, "max_daily": 250.0},
                "Streptococcal Pharyngitis (5-Day Alternative)": {"dose_mg_kg_day": 12.0, "freq": 1, "max_daily": 500.0}
            },
            "forms": {
                "Oral Suspension 200 mg / 5 mL": {"type": "liquid", "conc_mg": 200, "conc_ml": 5},
                "Oral Suspension 100 mg / 5 mL": {"type": "liquid", "conc_mg": 100, "conc_ml": 5},
                "Oral Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"}
            },
            "counseling": [
                "Tablets and immediate-release suspension can be taken with or without food.",
                "Avoid taking antacids containing aluminum or magnesium within 2 hours of this medication.",
                "Store the suspension at room temperature or in the refrigerator. Discard after 10 days."
            ]
        },
        "Domperidone": {
            "indications": {
                "GERD / Gastrointestinal Stasis (TID Dosing)": {"dose_mg_kg_dose": 0.4, "freq": 3, "max_single": 10.0, "max_daily": 30.0},
                "GERD / Prokinetic Agent (QID Dosing)": {"dose_mg_kg_dose": 0.3, "freq": 4, "max_single": 10.0, "max_daily": 30.0}
            },
            "forms": {
                "Oral Suspension 1 mg / 1 mL": {"type": "liquid", "conc_mg": 1, "conc_ml": 1},
                "Oral Suspension 5 mg / 1 mL": {"type": "liquid", "conc_mg": 5, "conc_ml": 1},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "Give 15-30 minutes before feeds/meals.",
                "Discontinue if there is no clinical response after 4 to 6 weeks.",
                "Risk of QT prolongation; an ECG is recommended before starting and 3-5 days after initiation for at-risk patients.",
                "May rarely cause acute dystonic reactions (involuntary twisting, uncontrolled blinking, or difficulty swallowing)."
            ]
        },
        "Cetirizine (Zyrtec)": {
            "indications": {
                "Allergic Rhinitis (Fixed Dose: 6mo - 2yrs)": {"fixed_dose_mg": 2.5, "freq": 1, "max_single": 2.5, "max_daily": 2.5},
                "Allergic Rhinitis (Fixed Dose: 2 - 5yrs)": {"fixed_dose_mg": 5.0, "freq": 1, "max_single": 5.0, "max_daily": 5.0},
                "Allergic Rhinitis (Fixed Dose: 6+ yrs)": {"fixed_dose_mg": 10.0, "freq": 1, "max_single": 10.0, "max_daily": 10.0}
            },
            "forms": {
                "Oral Liquid 5 mg / 5 mL": {"type": "liquid", "conc_mg": 5, "conc_ml": 5},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"},
                "Chewable Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"}
            },
            "counseling": [
                "May cause mild drowsiness. Often given in the evening.",
                "Can be taken with or without food."
            ]
        },
        "Loratadine (Claritin)": {
            "indications": {
                "Allergic Rhinitis (Fixed Dose: 2 - 5yrs)": {"fixed_dose_mg": 5.0, "freq": 1, "max_single": 5.0, "max_daily": 5.0},
                "Allergic Rhinitis (Fixed Dose: 6+ yrs)": {"fixed_dose_mg": 10.0, "freq": 1, "max_single": 10.0, "max_daily": 10.0}
            },
            "forms": {
                "Oral Liquid 5 mg / 5 mL": {"type": "liquid", "conc_mg": 5, "conc_ml": 5},
                "Chewable Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "Low sedation risk. Generally non-drowsy at recommended doses.",
                "Take once daily.",
                "Can be taken with or without food."
            ]
        },
        "Fexofenadine (Allegra)": {
            "indications": {
                "Allergic Rhinitis (Fixed Dose: 6mo - 2yrs)": {"fixed_dose_mg": 15.0, "freq": 2, "max_single": 15.0, "max_daily": 30.0},
                "Allergic Rhinitis (Fixed Dose: 2 - 11yrs)": {"fixed_dose_mg": 30.0, "freq": 2, "max_single": 30.0, "max_daily": 60.0},
                "Allergic Rhinitis (Fixed Dose: 12+ yrs / BID)": {"fixed_dose_mg": 60.0, "freq": 2, "max_single": 60.0, "max_daily": 120.0},
                "Allergic Rhinitis (Fixed Dose: 12+ yrs / Daily)": {"fixed_dose_mg": 180.0, "freq": 1, "max_single": 180.0, "max_daily": 180.0}
            },
            "forms": {
                "Oral Liquid 30 mg / 5 mL": {"type": "liquid", "conc_mg": 30, "conc_ml": 5},
                "Oral Tablet 30 mg": {"type": "solid", "strength_mg": 30, "unit": "tablet"},
                "Oral Tablet 60 mg": {"type": "solid", "strength_mg": 60, "unit": "tablet"},
                "Oral Tablet 180 mg": {"type": "solid", "strength_mg": 180, "unit": "tablet"}
            },
            "counseling": [
                "Minimal sedation risk.",
                "Do not take with fruit juices (like apple, orange, or grapefruit) as they decrease absorption.",
                "Shake oral suspension well before use."
            ]
        },
        "Levocetirizine (Xyzal)": {
            "indications": {
                "Allergic Rhinitis (Fixed Dose: 2 - 5yrs)": {"fixed_dose_mg": 2.5, "freq": 1, "max_single": 2.5, "max_daily": 2.5},
                "Allergic Rhinitis (Fixed Dose: 6 - 11yrs)": {"fixed_dose_mg": 5.0, "freq": 1, "max_single": 5.0, "max_daily": 5.0},
                "Allergic Rhinitis (Fixed Dose: 12+ yrs)": {"fixed_dose_mg": 5.0, "freq": 1, "max_single": 10.0, "max_daily": 10.0}
            },
            "forms": {
                "Oral Solution 2.5 mg / 5 mL": {"type": "liquid", "conc_mg": 2.5, "conc_ml": 5},
                "Oral Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"}
            },
            "counseling": [
                "May cause mild drowsiness; preferably take in the evening.",
                "Can be taken with or without food."
            ]
        },
        "Diphenhydramine (Benadryl)": {
            "indications": {
                "Allergic Reaction / Urticaria": {"dose_mg_kg_dose": 1.25, "freq": 4, "max_single": 50.0, "max_daily": 300.0}
            },
            "forms": {
                "Oral Liquid 12.5 mg / 5 mL": {"type": "liquid", "conc_mg": 12.5, "conc_ml": 5},
                "Chewable Tablet 12.5 mg": {"type": "solid", "strength_mg": 12.5, "unit": "tablet"},
                "Oral Capsule 25 mg": {"type": "solid", "strength_mg": 25, "unit": "capsule"}
            },
            "counseling": [
                "Will cause significant drowsiness. Do not use with other sedating medications.",
                "May cause paradoxical excitation in some young children.",
                "Can cause dry mouth."
            ]
        },
        "Omeprazole (Prilosec)": {
            "indications": {
                "GERD / Gastroesophageal Reflux": {"dose_mg_kg_day": 1.0, "freq": 1, "max_daily": 40.0},
                "Peptic Ulcer Disease": {"dose_mg_kg_day": 1.0, "freq": 1, "max_daily": 40.0}
            },
            "forms": {
                "Oral Suspension 2 mg / 1 mL": {"type": "liquid", "conc_mg": 2, "conc_ml": 1},
                "Delayed-Release Capsule 10 mg": {"type": "solid", "strength_mg": 10, "unit": "capsule"},
                "Delayed-Release Capsule 20 mg": {"type": "solid", "strength_mg": 20, "unit": "capsule"},
                "Delayed-Release Capsule 40 mg": {"type": "solid", "strength_mg": 40, "unit": "capsule"}
            },
            "counseling": [
                "Take 30 to 60 minutes before a meal, preferably before breakfast.",
                "Do not chew or crush delayed-release capsules. Swallow whole.",
                "If unable to swallow, capsules can be opened and granules sprinkled onto a spoonful of cold applesauce; swallow immediately without chewing."
            ]
        },
        "Ondansetron (Zofran)": {
            "indications": {
                "Acute Gastroenteritis Dehydration / Nausea": {"dose_mg_kg_dose": 0.15, "freq": 3, "max_single": 8.0, "max_daily": 24.0}
            },
            "forms": {
                "Oral Solution 4 mg / 5 mL": {"type": "liquid", "conc_mg": 4, "conc_ml": 5},
                "Orally Disintegrating Tablet (ODT) 4 mg": {"type": "solid", "strength_mg": 4, "unit": "tablet"},
                "Orally Disintegrating Tablet (ODT) 8 mg": {"type": "solid", "strength_mg": 8, "unit": "tablet"}
            },
            "counseling": [
                "For ODT: Remove from blister pack with dry hands immediately before use. Let it dissolve on the tongue and swallow with saliva.",
                "Can be taken with or without food.",
                "May cause mild headache, fatigue, or constipation."
            ]
        },
        "Ibuprofen": {
            "indications": {
                "Fever / Mild-to-Moderate Pain": {"dose_mg_kg_dose": 10.0, "freq": 3, "max_single": 400.0, "max_daily": 1200.0},
                "Inflammatory Pain / Juvenile Idiopathic Arthritis": {"dose_mg_kg_dose": 10.0, "freq": 4, "max_single": 600.0, "max_daily": 2400.0}
            },
            "forms": {
                "Infant Oral Drops 50 mg / 1.25 mL (40 mg/mL)": {"type": "liquid", "conc_mg": 50, "conc_ml": 1.25},
                "Children's Oral Suspension 100 mg / 5 mL": {"type": "liquid", "conc_mg": 100, "conc_ml": 5},
                "Chewable Tablet 100 mg": {"type": "solid", "strength_mg": 100, "unit": "tablet"},
                "Oral Tablet 200 mg": {"type": "solid", "strength_mg": 200, "unit": "tablet"}
            },
            "counseling": [
                "Take with food, milk, or meals to decrease upset stomach.",
                "Shake suspensions thoroughly before measuring.",
                "Ensure proper hydration when taking to protect kidney function."
            ]
        },
        "Acetaminophen (Paracetamol)": {
            "indications": {
                "Fever / Pain Management": {"dose_mg_kg_dose": 15.0, "freq": 4, "max_single": 1000.0, "max_daily": 4000.0}
            },
            "forms": {
                "Oral Suspension 160 mg / 5 mL": {"type": "liquid", "conc_mg": 160, "conc_ml": 5},
                "Chewable Tablet 160 mg": {"type": "solid", "strength_mg": 160, "unit": "tablet"},
                "Oral Tablet 500 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "Do not exceed 5 doses in 24 hours. Severe liver damage may occur if daily maximum is exceeded.",
                "Check the labels of other over-the-counter cough/cold products to ensure they do not also contain acetaminophen.",
                "Can be taken with or without food."
            ]
        }
    }

    @classmethod
    def calculate_from_diagnosis(cls, drug: str, diagnosis: str, form_name: str, weight_kg: float) -> Dict[str, Any]:
        drug_data = cls.GUIDELINES.get(drug, {})
        rule = drug_data.get("indications", {}).get(diagnosis)
        form = drug_data.get("forms", {}).get(form_name)
        counseling = drug_data.get("counseling", [])

        if not rule or not form:
            return {"error": "Selected indication or dosage form not found."}

        freq = rule.get("freq", 2)
        max_single = rule.get("max_single", 0.0)
        max_daily = rule.get("max_daily", 0.0)

        if "fixed_dose_mg" in rule:
            raw_single = rule["fixed_dose_mg"]
            raw_daily = raw_single * freq
        elif "dose_mg_kg_day" in rule:
            raw_daily = weight_kg * rule["dose_mg_kg_day"]
            raw_single = raw_daily / freq
        else:
            raw_single = weight_kg * rule["dose_mg_kg_dose"]
            raw_daily = raw_single * freq

        final_single = raw_single
        final_daily = raw_daily
        alerts = []

        if max_single > 0 and final_single > max_single:
            alerts.append(f"Calculated single dose ({raw_single:.1f} mg) capped at guideline max single ceiling ({max_single:.1f} mg).")
            final_single = max_single
            final_daily = final_single * freq

        if max_daily > 0 and final_daily > max_daily:
            alerts.append(f"Calculated daily dose ({final_daily:.1f} mg/day) capped at guideline max daily ceiling ({max_daily:.1f} mg/day).")
            final_daily = max_daily
            final_single = final_daily / freq

        dose_unit_str = ""
        form_calc_details = {}

        if form["type"] == "liquid":
            conc_mg = form["conc_mg"]
            conc_ml = form["conc_ml"]
            vol_single = final_single / (conc_mg / conc_ml)
            vol_daily = final_daily / (conc_mg / conc_ml)
            dose_unit_str = f"{vol_single:.2f} mL"
            form_calc_details = {
                "form_type": "liquid",
                "vol_single": vol_single,
                "vol_daily": vol_daily,
                "conc_str": f"{conc_mg} mg / {conc_ml} mL"
            }
        else:
            strength_mg = form["strength_mg"]
            unit_label = form.get("unit", "unit")
            count_single = final_single / strength_mg
            count_daily = final_daily / strength_mg
            dose_unit_str = f"{count_single:.2f} {unit_label}(s)"
            form_calc_details = {
                "form_type": "solid",
                "count_single": count_single,
                "count_daily": count_daily,
                "strength_str": f"{strength_mg} mg per {unit_label}"
            }

        return {
            "drug": drug,
            "diagnosis": diagnosis,
            "form_name": form_name,
            "final_single_mg": final_single,
            "final_daily_mg": final_daily,
            "dose_unit_str": dose_unit_str,
            "form_details": form_calc_details,
            "freq": freq,
            "interval_hours": round(24 / freq, 1),
            "alerts": alerts,
            "counseling": counseling
        }

class ClinicalReportGenerator:
    @staticmethod
    def _md_bold_to_html(text: str) -> str:
        escaped = html.escape(text)
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)

    @classmethod
    def generate_html_report(
        cls,
        patient_meta: Dict[str, str],
        dosing_summary: Optional[Dict[str, Any]],
        interaction_summary: Optional[Dict[str, Any]],
        monograph_data: Optional[Dict[str, Any]]
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        dosing_html = "<p><em>No diagnosis-driven dosing calculation recorded in this session.</em></p>"
        if dosing_summary:
            metrics_rows = "".join(f"<tr><th>{html.escape(k)}</th><td><strong>{html.escape(str(v))}</strong></td></tr>" for k, v in dosing_summary.get("metrics", {}).items())
            params_rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in dosing_summary.get("parameters", {}).items())
            alerts_html = f'<div class="alert-box"><strong>⚠️ Guideline Safety Alerts:</strong><ul>{"".join(f"<li>{cls._md_bold_to_html(a)}</li>" for a in dosing_summary["alerts"])}</ul></div>' if dosing_summary.get("alerts") else ""

            dosing_html = f"""
                <div class="section-subtitle">Indication / Diagnosis Engine: {html.escape(dosing_summary.get('mode', 'Standard'))}</div>
                {alerts_html}
                <div class="two-col">
                    <div><h4>Patient & Formulation Parameters</h4><table class="data-table">{params_rows}</table></div>
                    <div><h4>Calculated Regimen</h4><table class="data-table">{metrics_rows}</table></div>
                </div>
                <div class="sig-box"><strong>Prescription Sig Summary:</strong><br/>{cls._md_bold_to_html(dosing_summary.get('sig_summary', ''))}</div>
            """

        counsel_html = ""
        if dosing_summary and dosing_summary.get("counseling"):
            c_items = "".join(f"<li>{cls._md_bold_to_html(c)}</li>" for c in dosing_summary["counseling"])
            counsel_html = f'<div class="report-section"><h2>Patient Counseling & Education Requirements</h2><ul>{c_items}</ul></div>'

        inter_html = "<p><em>No multi-drug interaction analysis recorded in this session.</em></p>"
        if interaction_summary and interaction_summary.get("pair_results"):
            norm_rows = "".join(f"<tr><td>{html.escape(p['input_name'])}</td><td><strong>{html.escape(p['rxnorm']['normalized_name'].title())}</strong></td><td>{html.escape(p['rxnorm']['rxcui'])}</td><td>{'Loaded' if p.get('fda_data') else 'Class Rules Only'}</td></tr>" for p in interaction_summary.get("profiles", []))
            pair_cards = ""
            for res in interaction_summary["pair_results"]:
                rank = res["severity_rank"]
                card_cls = "pair-high" if rank == 2 else ("pair-mod" if rank == 1 else "pair-clear")
                badge = "MAJOR / CONTRAINDICATED" if rank == 2 else ("MODERATE / PRECAUTION" if rank == 1 else "NO DIRECT LABEL CONFLICT")
                findings_list = f"<ul>{''.join(f'<li><strong>[{html.escape(f['source'])}]:</strong> {cls._md_bold_to_html(f['excerpt'])}</li>' for f in res['findings'])}</ul>" if res["findings"] else ""
                pair_cards += f'<div class="pair-card {card_cls}"><div class="pair-header"><span class="badge">{badge}</span><strong>{html.escape(res["pair"])}</strong> — <em>{html.escape(res["severity"])}</em></div>{findings_list}</div>'

            inter_html = f'<h4>Evaluated Medication Regimen (RxNorm Standardized)</h4><table class="data-table"><thead><tr><th>Entered Name</th><th>Standardized Generic Ingredient</th><th>RxCUI</th><th>FDA Monograph</th></tr></thead><tbody>{norm_rows}</tbody></table><h4>Pairwise Interaction Findings ({len(interaction_summary["pair_results"])} Pairs Evaluated)</h4>{pair_cards}'

        mono_html = ""
        if monograph_data:
            boxed_html = f'<div class="pair-card pair-high"><strong>🛑 FDA BOXED WARNING:</strong><br/>{html.escape(monograph_data["boxed_warning"][:1200])}</div>' if monograph_data.get("boxed_warning") else ""
            mono_html = f"""
                <div class="report-section">
                    <h2>Primary Medication Monograph Highlights: {html.escape(monograph_data.get('generic_name', '').title())}</h2>
                    <table class="data-table">
                        <tr><th>Brand Name(s)</th><td>{html.escape(monograph_data.get('brand_name', 'N/A')[:100])}</td><th>Route(s)</th><td>{html.escape(monograph_data.get('route', 'N/A'))}</td></tr>
                        <tr><th>Pharmacologic Class</th><td>{html.escape(monograph_data.get('pharm_class', 'N/A')[:100])}</td><th>Manufacturer</th><td>{html.escape(monograph_data.get('manufacturer', 'N/A')[:80])}</td></tr>
                    </table>
                    {boxed_html}
                    <h4>Contraindications Summary</h4><p class="mono-excerpt">{html.escape(monograph_data.get('contraindications', 'N/A')[:900])}</p>
                    <h4>Dosage & Administration Overview</h4><p class="mono-excerpt">{html.escape(monograph_data.get('dosage_and_admin', 'N/A')[:900])}</p>
                </div>
            """

        notes_html = f'<div class="report-section"><h2>Clinical Assessment & Notes</h2><div class="sig-box">{html.escape(patient_meta.get("clinical_notes", "")).replace(chr(10), "<br/>")}</div></div>' if patient_meta.get("clinical_notes") else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Clinical Indication-Driven Dosing Report</title>
    <style>
        :root {{ --primary: #1a365d; --border: #cbd5e1; --bg-light: #f8fafc; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; line-height: 1.45; margin: 0; padding: 25px; font-size: 13px; }}
        .report-container {{ max-width: 900px; margin: 0 auto; }}
        .print-banner {{ background: #eef2ff; border: 1px solid #c7d2fe; padding: 10px 15px; border-radius: 6px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
        .print-btn {{ background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px; }}
        .report-header {{ border-bottom: 3px solid var(--primary); padding-bottom: 12px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: flex-end; }}
        .report-header h1 {{ margin: 0; color: var(--primary); font-size: 22px; }}
        .meta-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; background: var(--bg-light); border: 1px solid var(--border); padding: 12px; border-radius: 6px; margin-bottom: 20px; }}
        .meta-item label {{ display: block; font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
        .meta-item span {{ font-weight: 700; font-size: 13.5px; color: #0f172a; }}
        .report-section {{ margin-bottom: 22px; page-break-inside: avoid; }}
        h2 {{ color: var(--primary); font-size: 16px; border-bottom: 1px solid var(--border); padding-bottom: 5px; margin-top: 0; margin-bottom: 12px; }}
        h4 {{ margin: 10px 0 6px 0; font-size: 13px; color: #334155; }}
        .section-subtitle {{ font-weight: 600; color: #475569; margin-bottom: 10px; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }}
        .data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 12.5px; }}
        .data-table th, .data-table td {{ border: 1px solid var(--border); padding: 6px 10px; text-align: left; }}
        .data-table th {{ background: var(--bg-light); font-weight: 600; width: 42%; }}
        .sig-box {{ background: #f0f9ff; border-left: 4px solid #0284c7; padding: 10px 14px; border-radius: 4px; margin-top: 8px; }}
        .alert-box {{ background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 12px; margin-bottom: 10px; color: #92400e; }}
        .pair-card {{ border: 1px solid var(--border); border-radius: 5px; padding: 10px 14px; margin-bottom: 10px; page-break-inside: avoid; }}
        .pair-high {{ background: #fef2f2; border-left: 5px solid #dc2626; }}
        .pair-mod {{ background: #fffbeb; border-left: 5px solid #d97706; }}
        .pair-clear {{ background: #f0fdf4; border-left: 5px solid #16a34a; }}
        .badge {{ display: inline-block; padding: 2px 6px; font-size: 10.5px; font-weight: 700; border-radius: 3px; margin-right: 6px; background: rgba(0,0,0,0.08); }}
        .mono-excerpt {{ background: var(--bg-light); border: 1px solid var(--border); padding: 8px 12px; border-radius: 4px; font-size: 12px; white-space: pre-line; }}
        .counseling-box {{ background-color: #e0f2fe; border-left: 6px solid #0284c7; padding: 15px; border-radius: 5px; color: #075985; margin-top: 15px; font-size: 13px; }}
        .counseling-box ul {{ margin: 0; padding-left: 20px; }}
        .signoff-grid {{ margin-top: 35px; padding-top: 15px; border-top: 1px solid var(--border); display: grid; grid-template-columns: 1fr 1fr; gap: 40px; page-break-inside: avoid; }}
        .sig-line {{ border-bottom: 1px solid #475569; height: 28px; margin-bottom: 4px; }}
        .disclaimer-footer {{ margin-top: 25px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 10px; }}
        @media print {{ body {{ padding: 0; }} .no-print {{ display: none !important; }} }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="print-banner no-print">
            <span>📄 <strong>Print-Ready Clinical Report:</strong> Click to save as PDF or print.</span>
            <button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
        </div>
        <div class="report-header">
            <div>
                <h1>Clinical Indication-Driven Dosing Report</h1>
                <div class="sub">Guideline-Based Dosing Engine (Weight, Age & Diagnosis)</div>
            </div>
            <div style="text-align: right; font-size: 12px; color: #475569;"><strong>Date:</strong> {timestamp}</div>
        </div>
        <div class="meta-grid">
            <div class="meta-item"><label>Patient Name</label><span>{html.escape(patient_meta.get('patient_name', ''))}</span></div>
            <div class="meta-item"><label>Age / Weight</label><span>{html.escape(patient_meta.get('age_sex', ''))} | {html.escape(patient_meta.get('anthropometrics', ''))}</span></div>
            <div class="meta-item"><label>Indication</label><span>{html.escape(patient_meta.get('indication', ''))}</span></div>
            <div class="meta-item"><label>Clinician</label><span>{html.escape(patient_meta.get('clinician_name', ''))}</span></div>
        </div>
        <div class="report-section"><h2>1. Indication-Driven Dosing Regimen</h2>{dosing_html}</div>
        {counsel_html}
        <div class="report-section"><h2>2. Multi-Drug Interaction Analysis</h2>{inter_html}</div>
        {mono_html}
        {notes_html}
        <div class="signoff-grid">
            <div><div class="sig-line"></div><strong>Clinician Signature:</strong></div>
            <div><div class="sig-line"></div><strong>Date & Stamp</strong></div>
        </div>
        <div class="disclaimer-footer">Clinical Decision Support Tool — Verify all calculations against institutional protocols.</div>
    </div>
</body>
</html>"""

def main():
    st.title("💊 Clinical Indication-Driven Dosing System")
    
    tab_dosing, tab_monograph, tab_interactions, tab_report = st.tabs([
        "🎯 Indication Dosing",
        "📄 FDA Monograph",
        "⚡ Interaction Checker",
        "📥 Print Report"
    ])

    with tab_dosing:
        col_in, col_out = st.columns([1, 1])

        with col_in:
            st.markdown("#### 1. Patient Demographics")
            a_col1, a_col2 = st.columns([2, 1])
            age_unit = a_col2.selectbox("Age Unit", ["Years", "Months"], index=0)
            age_val = a_col1.number_input("Patient Age", min_value=0.0, max_value=216.0, value=5.0, step=0.5)

            w_col1, w_col2 = st.columns([2, 1])
            weight_val = w_col1.number_input("Patient Weight", min_value=0.5, max_value=300.0, value=18.0, step=0.5)
            weight_unit = w_col2.selectbox("Weight Unit", ["kg", "lbs"])
            weight_kg = weight_val if weight_unit == "kg" else weight_val / 2.20462

            peds_validation = PediatricWeightValidator.validate_pediatric_weight(age_val, age_unit, weight_kg)
            allow_calc = True

            if peds_validation["status"] == "critical":
                for msg in peds_validation["messages"]: st.error(msg)
                allow_calc = st.checkbox("⚠️ Clinician Override: Confirm entered weight is accurate.", value=False)
            elif peds_validation["status"] == "warning":
                for msg in peds_validation["messages"]: st.warning(msg)

            st.markdown("#### 2. Medication, Indication & Formulation")
            # Sort medications alphabetically
            available_drugs = sorted(list(IndicationDosingEngine.GUIDELINES.keys()))
            selected_drug = st.selectbox("Select Medication", available_drugs)
            
            available_diagnoses = list(IndicationDosingEngine.GUIDELINES[selected_drug]["indications"].keys())
            selected_diagnosis = st.selectbox("Select Indication", available_diagnoses)

            available_forms = list(IndicationDosingEngine.GUIDELINES[selected_drug]["forms"].keys())
            selected_form = st.selectbox("Select Dosage Form / Strength", available_forms)

        with col_out:
            st.markdown("#### 3. Guideline Regimen")
            if not allow_calc:
                st.info("🔒 Calculation paused due to weight plausibility warning. Check override box to proceed.")
            else:
                res = IndicationDosingEngine.calculate_from_diagnosis(selected_drug, selected_diagnosis, selected_form, weight_kg)
                if "error" in res:
                    st.error(res["error"])
                else:
                    for alert in res["alerts"]: st.warning(f"⚠️ {alert}")
                    r1, r2 = st.columns(2)
                    r1.metric("Single Dose", f"{res['final_single_mg']:.1f} mg")
                    r2.metric("Total Daily Dose", f"{res['final_daily_mg']:.1f} mg/day")

                    fd = res["form_details"]
                    f1, f2 = st.columns(2)
                    if fd["form_type"] == "liquid":
                        f1.metric("Liquid Volume / Dose", f"{fd['vol_single']:.2f} mL", f"Every {res['interval_hours']} hours")
                        f2.metric("Total Daily Volume", f"{fd['vol_daily']:.2f} mL/day", f"{fd['conc_str']}")
                        sig_form_desc = f"**{fd['vol_single']:.2f} mL** of {fd['conc_str']}"
                    else:
                        unit_lbl = selected_form.split()[-1]
                        f1.metric("Form Units / Dose", f"{fd['count_single']:.2f} {unit_lbl}(s)", f"Every {res['interval_hours']} hours")
                        f2.metric("Total Daily Units", f"{fd['count_daily']:.2f} {unit_lbl}(s)/day", f"{fd['strength_str']}")
                        sig_form_desc = f"**{fd['count_single']:.2f} {unit_lbl}(s)** ({fd['strength_str']})"

                    sig_summary = f"Administer **{res['final_single_mg']:.1f} mg** ({sig_form_desc}) every **{res['interval_hours']} hours** ({res['freq']}x daily) for **{selected_diagnosis}**."
                    st.info(f"**Prescription Sig Summary:**\n\n{sig_summary}")

                    if res.get("counseling"):
                        st.markdown("#### 🗣️ Patient Counseling & Education")
                        counseling_html = "<ul>" + "".join([f"<li>{c}</li>" for c in res["counseling"]]) + "</ul>"
                        st.markdown(f'<div class="counseling-box">{counseling_html}</div>', unsafe_allow_html=True)

                    st.session_state.latest_dosing = {
                        "mode": f"{selected_drug} Guideline Dosing",
                        "parameters": {
                            "Medication": selected_drug,
                            "Indication": selected_diagnosis,
                            "Dosage Form": selected_form,
                            "Patient Age": f"{age_val:g} {age_unit.lower()}",
                            "Patient Weight": f"{weight_kg:.2f} kg"
                        },
                        "metrics": {
                            "Single Dose": f"{res['final_single_mg']:.1f} mg",
                            "Total Daily Dose": f"{res['final_daily_mg']:.1f} mg/day",
                            "Prescribed Amount / Dose": res["dose_unit_str"]
                        },
                        "alerts": res["alerts"],
                        "sig_summary": sig_summary,
                        "counseling": res.get("counseling", [])
                    }
                    st.session_state.latest_indication = selected_diagnosis

            # AUTO-FETCH FDA MONOGRAPH BASED ON DROPDOWN SELECTION
            api_search_term = selected_drug.split(" (")[0]
            if st.session_state.get("last_fetched_drug") != selected_drug:
                with st.spinner(f"Auto-fetching FDA Monograph for {api_search_term}..."):
                    st.session_state.drug_data = DrugDataClient.fetch_drug_label(api_search_term)
                    st.session_state.last_fetched_drug = selected_drug

    with tab_monograph:
        data = st.session_state.get("drug_data")
        if not data:
            st.warning(f"No FDA Monograph found in the OpenFDA database for '{api_search_term}'.")
        else:
            st.subheader(data['generic_name'].title())
            st.write(data['indications'])
            if data['boxed_warning']: st.markdown(f'<div class="boxed-warning"><h4>🛑 Boxed Warning</h4>{data["boxed_warning"][:1000]}</div>', unsafe_allow_html=True)
            with st.expander("Dosage & Administration Guidelines"):
                st.write(data['dosage_and_admin'])
            with st.expander("Contraindications & Warnings"):
                st.write(data['contraindications'])
                st.write(data['warnings'])

    with tab_interactions:
        st.subheader("⚡ Pairwise Interaction Checker")
        med_input = st.text_area("Enter medications (comma-separated):", value="Warfarin, Omeprazole")
        if st.button("Check Interactions"):
            meds = [m.strip() for m in med_input.split(",") if m.strip()]
            profiles = [{"input_name": m, "rxnorm": DrugDataClient.resolve_rxnorm_ingredient(m), "fda_data": DrugDataClient.fetch_drug_label(m)} for m in meds]
            results = [PairwiseInteractionEngine.evaluate_pair(a, b) for a, b in list(combinations(profiles, 2))]
            st.session_state.latest_interactions = {"profiles": profiles, "pair_results": results}
            for r in results:
                st.markdown(f"**{r['pair']}** — *{r['severity']}*")
                for f in r["findings"]: st.write(f"- {f['excerpt']}")

    with tab_report:
        st.subheader("📥 Export & Print Report")
        col_meta1, col_meta2 = st.columns(2)
        with col_meta1:
            pt_name = st.text_input("Patient Name", value="Patient #402")
            pt_meta_str = st.text_input("Age / Sex", value="5 yrs / Male")
        with col_meta2:
            pt_anthro_str = st.text_input("Weight Summary", value="18.0 kg")
            clinician = st.text_input("Clinician Name", value="Clinician")
        notes = st.text_area("Notes", value="Verified indication-driven dosing & patient counseling points.")

        html_out = ClinicalReportGenerator.generate_html_report(
            {"patient_name": pt_name, "age_sex": pt_meta_str, "anthropometrics": pt_anthro_str, "clinician_name": clinician, "indication": st.session_state.get('latest_indication', ''), "clinical_notes": notes},
            st.session_state.get("latest_dosing"),
            st.session_state.get("latest_interactions"),
            st.session_state.get("drug_data")
        )

        st.download_button("📥 Download HTML Report", data=html_out, file_name="clinical_dosing_report.html", mime="text/html", type="primary")
        st.components.v1.html(html_out, height=600, scrolling=True)

if __name__ == "__main__":
    main()
