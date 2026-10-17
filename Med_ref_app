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
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .warning-box { background-color: #fff3cd; border-left: 6px solid #ffecb5; padding: 15px; border-radius: 5px; color: #664d03; margin-bottom: 20px; }
    .boxed-warning { background-color: #f8d7da; border-left: 6px solid #dc3545; padding: 15px; border-radius: 5px; color: #842029; margin-bottom: 20px; }
    .interaction-high { background-color: #f8d7da; border-left: 6px solid #dc3545; padding: 12px 15px; border-radius: 5px; color: #842029; margin-bottom: 12px; }
    .interaction-moderate { background-color: #fff3cd; border-left: 6px solid #ffc107; padding: 12px 15px; border-radius: 5px; color: #664d03; margin-bottom: 12px; }
    .interaction-clear { background-color: #d1e7dd; border-left: 6px solid #198754; padding: 12px 15px; border-radius: 5px; color: #0f5132; margin-bottom: 12px; }
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
            f'openfda.generic_name.exact:"{clean_name.upper()}"+openfda.brand_name.exact:"{clean_name.upper()}"',
            f'openfda.generic_name:"{clean_name}"+openfda.brand_name:"{clean_name}"'
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
    }

    CURATED_CLINICAL_RULES = [
        {
            "group_a": ["warfarin", "apixaban", "rivaroxaban", "dabigatran"],
            "group_b": ["ibuprofen", "naproxen", "diclofenac", "ketorolac", "meloxicam", "aspirin"],
            "severity": "Major / High Risk",
            "summary": "Increased risk of serious gastrointestinal and systemic bleeding due to additive antiplatelet/mucosal effects with anticoagulation."
        },
        {
            "group_a": ["sildenafil", "tadalafil", "vardenafil"],
            "group_b": ["nitroglycerin", "isosorbide mononitrate", "isosorbide dinitrate"],
            "severity": "Contraindicated",
            "summary": "Synergistic vasodilation via the nitric oxide-cGMP pathway can cause profound, life-threatening hypotension."
        },
        {
            "group_a": ["simvastatin", "lovastatin", "atorvastatin"],
            "group_b": ["clarithromycin", "erythromycin", "itraconazole", "ketoconazole", "gemfibrozil"],
            "severity": "Contraindicated / Major",
            "summary": "Potent CYP3A4/OATP1B1 inhibition markedly elevates statin plasma concentrations, increasing the risk of myopathy and rhabdomyolysis."
        },
        {
            "group_a": ["lisinopril", "enalapril", "ramipril", "losartan", "valsartan"],
            "group_b": ["spironolactone", "eplerenone", "amiloride", "triamterene", "potassium chloride"],
            "severity": "Major / Monitor Closely",
            "summary": "Additive hyperkalemic effects. Concurrent use increases the risk of severe, potentially fatal hyperkalemia, especially in renal impairment."
        },
        {
            "group_a": ["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "venlafaxine", "duloxetine"],
            "group_b": ["phenelzine", "tranylcypromine", "selegiline", "linezolid", "tramadol", "sumatriptan"],
            "severity": "Major / Serotonin Syndrome Risk",
            "summary": "Concurrent serotonergic agents significantly elevate the risk of serotonin syndrome (hyperthermia, autonomic instability, neuromuscular clonus)."
        },
        {
            "group_a": ["morphine", "oxycodone", "hydrocodone", "fentanyl", "methadone", "tramadol"],
            "group_b": ["alprazolam", "lorazepam", "diazepam", "clonazepam", "zolpidem"],
            "severity": "Major (Boxed Warning)",
            "summary": "Concomitant use of opioids with benzodiazepines or CNS depressants may result in profound sedation, respiratory depression, coma, and death."
        },
        {
            "group_a": ["methotrexate"],
            "group_b": ["amoxicillin", "penicillin", "piperacillin", "ibuprofen", "naproxen", "trimethoprim", "sulfamethoxazole"],
            "severity": "Major",
            "summary": "Reduced renal tubular secretion or additive folate antagonism can lead to severe methotrexate toxicity (myelosuppression, mucositis)."
        },
        {
            "group_a": ["digoxin"],
            "group_b": ["amiodarone", "verapamil", "diltiazem", "clarithromycin", "spironolactone"],
            "severity": "Major",
            "summary": "P-glycoprotein inhibition or reduced renal clearance increases serum digoxin levels by 50–100%, predisposing to digitalis toxicity and arrhythmias."
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
            "Acute Otitis Media (Standard Dose)": {"dose_mg_kg_day": 45.0, "freq": 2, "max_daily": 1750.0, "conc_mg": 400, "conc_ml": 5},
            "Acute Otitis Media (High Dose / Resistant S. pneumoniae)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_daily": 4000.0, "conc_mg": 400, "conc_ml": 5},
            "Streptococcal Pharyngitis (Strep Throat)": {"dose_mg_kg_day": 50.0, "freq": 2, "max_daily": 1000.0, "conc_mg": 250, "conc_ml": 5},
            "Acute Sinusitis": {"dose_mg_kg_day": 45.0, "freq": 2, "max_daily": 2000.0, "conc_mg": 400, "conc_ml": 5}
        },
        "Ibuprofen": {
            "Fever / Mild-to-Moderate Pain": {"dose_mg_kg_dose": 10.0, "freq": 3, "max_single": 400.0, "max_daily": 1200.0, "conc_mg": 100, "conc_ml": 5},
            "Inflammatory Pain / Juvenile Arthritis": {"dose_mg_kg_dose": 10.0, "freq": 4, "max_single": 600.0, "max_daily": 2400.0, "conc_mg": 100, "conc_ml": 5}
        },
        "Acetaminophen (Paracetamol)": {
            "Fever / Pain Management": {"dose_mg_kg_dose": 15.0, "freq": 4, "max_single": 1000.0, "max_daily": 4000.0, "conc_mg": 160, "conc_ml": 5}
        },
        "Azithromycin": {
            "Community-Acquired Pneumonia / Bronchitis (Day 1)": {"dose_mg_kg_day": 10.0, "freq": 1, "max_daily": 500.0, "conc_mg": 200, "conc_ml": 5},
            "Pharyngitis / Tonsillitis (Alternative)": {"dose_mg_kg_day": 12.0, "freq": 1, "max_daily": 500.0, "conc_mg": 200, "conc_ml": 5}
        }
    }

    @classmethod
    def calculate_from_diagnosis(cls, drug: str, diagnosis: str, weight_kg: float) -> Dict[str, Any]:
        rule = cls.GUIDELINES.get(drug, {}).get(diagnosis)
        if not rule:
            return {"error": "Selected indication guideline not found."}

        conc_mg = rule.get("conc_mg", 0)
        conc_ml = rule.get("conc_ml", 1)
        freq = rule.get("freq", 2)
        max_single = rule.get("max_single", 0.0)
        max_daily = rule.get("max_daily", 0.0)

        if "dose_mg_kg_day" in rule:
            raw_daily = weight_kg * rule["dose_mg_kg_day"]
            raw_single = raw_daily / freq
        else:
            raw_single = weight_kg * rule["dose_mg_kg_dose"]
            raw_daily = raw_single * freq

        final_single = raw_single
        final_daily = raw_daily
        alerts = []

        if max_single > 0 and final_single > max_single:
            alerts.append(f"Calculated single dose ({raw_single:.1f} mg) capped at maximum single limit ({max_single:.1f} mg).")
            final_single = max_single
            final_daily = final_single * freq

        if max_daily > 0 and final_daily > max_daily:
            alerts.append(f"Calculated daily dose ({final_daily:.1f} mg/day) capped at maximum daily limit ({max_daily:.1f} mg/day).")
            final_daily = max_daily
            final_single = final_daily / freq

        vol_single = (final_single / (conc_mg / conc_ml)) if conc_mg > 0 else 0.0
        vol_daily = (final_daily / (conc_mg / conc_ml)) if conc_mg > 0 else 0.0

        return {
            "drug": drug,
            "diagnosis": diagnosis,
            "final_single_mg": final_single,
            "final_daily_mg": final_daily,
            "volume_per_dose_ml": vol_single,
            "volume_daily_ml": vol_daily,
            "freq": freq,
            "interval_hours": round(24 / freq, 1),
            "conc_mg": conc_mg,
            "conc_ml": conc_ml,
            "alerts": alerts
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
                    <div><h4>Patient & Indication Parameters</h4><table class="data-table">{params_rows}</table></div>
                    <div><h4>Calculated Regimen</h4><table class="data-table">{metrics_rows}</table></div>
                </div>
                <div class="sig-box"><strong>Prescription Sig Summary:</strong><br/>{cls._md_bold_to_html(dosing_summary.get('sig_summary', ''))}</div>
            """

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
                    <h2>3. Primary Medication Monograph Highlights: {html.escape(monograph_data.get('generic_name', '').title())}</h2>
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
    
    with st.sidebar:
        st.header("🔍 Single Drug Lookup")
        search_query = st.text_input("Enter Generic or Brand Name", value="Amoxicillin")
        search_btn = st.button("Pull Drug Monograph", type="primary", use_container_width=True)

    if "drug_data" not in st.session_state or search_btn:
        with st.spinner(f"Querying OpenFDA database for '{search_query}'..."):
            st.session_state.drug_data = DrugDataClient.fetch_drug_label(search_query)
            st.session_state.last_query = search_query

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

            st.markdown("#### 2. Indication Selection")
            available_drugs = list(IndicationDosingEngine.GUIDELINES.keys())
            selected_drug = st.selectbox("Select Medication", available_drugs)
            available_diagnoses = list(IndicationDosingEngine.GUIDELINES[selected_drug].keys())
            selected_diagnosis = st.selectbox("Select Indication", available_diagnoses)

        with col_out:
            st.markdown("#### 3. Guideline Regimen")
            if not allow_calc:
                st.info("🔒 Calculation paused due to weight plausibility warning. Check override box to proceed.")
            else:
                res = IndicationDosingEngine.calculate_from_diagnosis(selected_drug, selected_diagnosis, weight_kg)
                if "error" in res:
                    st.error(res["error"])
                else:
                    for alert in res["alerts"]: st.warning(f"⚠️ {alert}")
                    r1, r2 = st.columns(2)
                    r1.metric("Single Dose", f"{res['final_single_mg']:.1f} mg")
                    r2.metric("Total Daily Dose", f"{res['final_daily_mg']:.1f} mg/day")

                    if res["volume_per_dose_ml"] > 0:
                        v1, v2 = st.columns(2)
                        v1.metric("Suspension Volume/Dose", f"{res['volume_per_dose_ml']:.2f} mL", f"Every {res['interval_hours']} hours")
                        v2.metric("Total Daily Volume", f"{res['volume_daily_ml']:.2f} mL/day", f"Using {res['conc_mg']}mg/{res['conc_ml']}mL")

                    sig_summary = f"Administer **{res['final_single_mg']:.1f} mg** " + (f"(**{res['volume_per_dose_ml']:.1f} mL** of {res['conc_mg']}mg/{res['conc_ml']}mL suspension) " if res["volume_per_dose_ml"] > 0 else "") + f"every **{res['interval_hours']} hours** ({res['freq']}x daily) for **{selected_diagnosis}**."
                    st.info(f"**Prescription Sig Summary:**\n\n{sig_summary}")

                    st.session_state.latest_dosing = {
                        "mode": f"{selected_drug} Guideline Dosing",
                        "parameters": {"Medication": selected_drug, "Indication": selected_diagnosis, "Patient Age": f"{age_val:g} {age_unit.lower()}", "Patient Weight": f"{weight_kg:.2f} kg"},
                        "metrics": {"Single Dose": f"{res['final_single_mg']:.1f} mg", "Total Daily Dose": f"{res['final_daily_mg']:.1f} mg/day", "Volume per Dose": f"{res['volume_per_dose_ml']:.2f} mL" if res['volume_per_dose_ml'] > 0 else "N/A"},
                        "alerts": res["alerts"],
                        "sig_summary": sig_summary
                    }
                    st.session_state.latest_indication = selected_diagnosis

    with tab_monograph:
        data = st.session_state.get("drug_data")
        if not data:
            st.error("No monograph loaded.")
        else:
            st.subheader(data['generic_name'].title())
            st.write(data['indications'])
            if data['boxed_warning']: st.markdown(f'<div class="boxed-warning"><h4>🛑 Boxed Warning</h4>{data["boxed_warning"][:1000]}</div>', unsafe_allow_html=True)

    with tab_interactions:
        st.subheader("⚡ Pairwise Interaction Checker")
        med_input = st.text_area("Enter medications (comma-separated):", value="Warfarin, Ibuprofen")
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
            clinician = st.text_input("Clinician Name", value="Clinical Pharmacist")
        notes = st.text_area("Notes", value="Verified indication-driven dosing.")

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
