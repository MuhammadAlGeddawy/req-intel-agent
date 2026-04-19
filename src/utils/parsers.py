import re
from typing import List, Dict

# Mapping requirement ID codes to your required Domain categories
DOMAIN_MAP = {
    "SYS": "SYSTEM",
    "HW": "HARDWARE",
    "SW": "SOFTWARE",
    "SAF": "SAFETY",
    "TST": "TEST"
}

def extract_requirements(raw_text: str) -> List[Dict]:
    """Extract requirements from raw document text using regex."""
    # Regex Pattern Breakdown:
    # (REQ-([A-Z]+)-\d+) -> Group 1: Full ID, Group 2: Domain Code (SYS/HW/etc)
    # :\s* -> Matches the colon and any trailing whitespace
    # (.+?)              -> Group 3: The requirement text (non-greedy)
    # (?=\nREQ-|\n#|\Z)  -> Lookahead: Stop at next REQ, next Header, or End of String
    pattern = r"(REQ-([A-Z]+)-\d+):\s*(.+?)(?=\nREQ-|\n#|\Z)"
    
    # Use re.DOTALL if requirements span multiple lines; 
    # otherwise, default is fine for single-line entries
    matches = re.finditer(pattern, raw_text, re.MULTILINE | re.DOTALL)

    requirements = []
    for match in matches:
        full_id = match.group(1)
        domain_code = match.group(2)
        text = match.group(3).strip()
        
        # Determine domain based on ID; default to SYSTEM if unknown
        domain = DOMAIN_MAP.get(domain_code, "SYSTEM")
        
        requirements.append({
            "id": full_id,
            "text": text,
            "domain": domain
        })

    return requirements