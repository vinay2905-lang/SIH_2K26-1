"""Synthetic institutions and applications with planted problems for the demo.

Nothing here describes a real institution, person or certificate.
"""

INSTITUTIONS = [
    dict(id="INST-VCE", aicte_id="1-2711034", name="Vidyaprakash College of Engineering", kind="Engineering",
         state="Maharashtra", state_code="MH", city="Pune", address="Survey No. 214, Maan Road, Pune 411057",
         region="Western", lat=18.5913, lon=73.7389, established=2001, university="Sahyadri Technological University",
         username="vce.pune", principal="Dr. Meera Kulkarni", trust="Vidyaprakash Education Trust"),
    dict(id="INST-GIT", aicte_id="1-3104562", name="Gulmohar Institute of Technology", kind="Engineering",
         state="Rajasthan", state_code="RJ", city="Jaipur", address="Plot 7, Sitapura Institutional Area, Jaipur 302022",
         region="Northern", lat=26.7835, lon=75.8233, established=2008, university="Aravalli Technical University",
         username="git.jaipur", principal="Dr. Kavita Rathore", trust="Gulmohar Shiksha Samiti"),
    dict(id="INST-NVP", aicte_id="1-2290871", name="Narmada Valley Institute of Pharmacy", kind="Pharmacy",
         state="Madhya Pradesh", state_code="MP", city="Indore", address="Khandwa Road, Indore 452017",
         region="Central", lat=22.6802, lon=75.8761, established=2005, university="Malwa Technical University",
         username="nvp.indore", principal="Dr. Rakesh Verma", trust="Narmada Valley Education Society"),
    dict(id="INST-KSM", aicte_id="1-1987345", name="Kayal School of Management", kind="Management",
         state="Kerala", state_code="KL", city="Kochi", address="Seaport-Airport Road, Kakkanad, Kochi 682030",
         region="South-Western", lat=10.0159, lon=76.3419, established=1999, university="Periyar Technological University",
         username="ksm.kochi", principal="Dr. Anitha Menon", trust="Kayal Educational Foundation"),
    dict(id="INST-SIE", aicte_id="1-3341209", name="Sahyog Institute of Engineering", kind="Engineering",
         state="Uttar Pradesh", state_code="UP", city="Lucknow", address="Sector 9, Faizabad Road, Lucknow 226028",
         region="Northern", lat=26.8807, lon=81.0218, established=2010, university="Avadh Technical University",
         username="sie.lucknow", principal="Dr. Alok Srivastava", trust="Sahyog Shiksha Trust"),
    dict(id="INST-WGP", aicte_id="1-1450298", name="Wainganga Polytechnic", kind="Polytechnic",
         state="Maharashtra", state_code="MH", city="Nagpur", address="Hingna Road, Nagpur 440016",
         region="Western", lat=21.1145, lon=78.9800, established=1994, university="Vidarbha Board of Technical Education",
         username="wgp.nagpur", principal="Shri. Prakash Deshmukh", trust="Wainganga Technical Education Society"),
    dict(id="INST-TCE", aicte_id="1-2560417", name="Tungabhadra College of Engineering", kind="Engineering",
         state="Karnataka", state_code="KA", city="Hubballi", address="Gokul Road, Hubballi 580030",
         region="South-Western", lat=15.3478, lon=75.1338, established=2003, university="Kittur Technological University",
         username="tce.hubballi", principal="Dr. Suresh Patil", trust="Tungabhadra Vidya Samsthe"),
    dict(id="INST-SIT", aicte_id="1-3718820", name="Shivalik Institute of Technology", kind="Engineering",
         state="Uttarakhand", state_code="UK", city="Dehradun", address="Sahastradhara Road, Dehradun 248001",
         region="Northern", lat=30.3570, lon=78.0860, established=2012, university="Doon Technical University",
         username="sit.dehradun", principal="Dr. Neha Bisht", trust="Shivalik Education Trust"),
]

OFFICIALS = [
    dict(username="a.kulkarni", full_name="A. Kulkarni", role="scrutinizer", region="Western"),
    dict(username="r.iyer", full_name="R. Iyer", role="scrutinizer", region="South-Western"),
    dict(username="r.menon", full_name="R. Menon", role="senior_officer", region="All"),
    dict(username="s.rao", full_name="S. Rao", role="rule_admin", region="All"),
    dict(username="auditor", full_name="Internal Auditor", role="auditor", region="All"),
]

DEMO_PASSWORD = "Pramaan@2026"

# approved programmes (AICTE records, cycle 2025-26) and what each application asks for
APPLICATIONS = {
    "INST-WGP": dict(id="APP-2026-00087", app_type="EOA", submitted="2026-04-10T04:35:00",
                     approved=[("Diploma in Mechanical Engineering", "Diploma", 60), ("Diploma in Civil Engineering", "Diploma", 60),
                               ("Diploma in Computer Engineering", "Diploma", 60)], requested=None,
                     fire_till="2027-03-31", outcome="approved"),
    "INST-SIE": dict(id="APP-2026-00231", app_type="EOA", submitted="2026-04-11T09:50:00",
                     approved=[("B.Tech Computer Science and Engineering", "UG", 120), ("B.Tech Electrical Engineering", "UG", 60),
                               ("B.Tech Information Technology", "UG", 60)], requested=None, fire_till="2027-03-31",
                     computers=70, ter_status="FAILED", bcc_modified=True),
    "INST-KSM": dict(id="APP-2026-00203", app_type="EOA", submitted="2026-04-12T06:15:00",
                     approved=[("MBA Business Administration", "PG", 120)], requested=None, fire_till="2027-06-30",
                     nba_till="2025-12-31", photos_far=True, bcc_unsigned=True, bcc_area=9800, form_area=10400,
                     outcome="letter"),
    "INST-NVP": dict(id="APP-2026-00112", app_type="INTAKE_INCREASE", submitted="2026-04-13T04:00:00",
                     approved=[("B.Pharm Pharmacy", "UG", 100), ("M.Pharm Pharmaceutics", "PG", 15)],
                     requested={"B.Pharm Pharmacy": 120}, affiliation_override={"B.Pharm Pharmacy": 120},
                     fire_till="2027-03-31", scanned_affidavit=True, university_down=True),
    "INST-GIT": dict(id="APP-2026-00150", app_type="NEW_PROGRAMME", submitted="2026-04-14T10:40:00",
                     approved=[("B.Tech Computer Science and Engineering", "UG", 120),
                               ("B.Tech Electronics and Communication Engineering", "UG", 60)],
                     new_programmes=[("B.Tech Artificial Intelligence and Data Science", "UG", 60)],
                     requested=None, fire_till="2026-03-31", fire_tampered_to="2027-03-31", form_fire="2027-03-31"),
    "INST-VCE": dict(id="APP-2026-00045", app_type="EOA", submitted="2026-04-15T07:06:00",
                     approved=[("B.Tech Computer Science and Engineering", "UG", 120), ("B.Tech Mechanical Engineering", "UG", 60),
                               ("B.Tech Civil Engineering", "UG", 60), ("M.Tech Structural Engineering", "PG", 18)],
                     requested={"B.Tech Computer Science and Engineering": 180}, fire_till="2026-03-31",
                     form_fire="2027-03-31", skip=["STRUCTURAL_STABILITY"], unknown_faculty=2, duplicate_photo_from="INST-WGP"),
    "INST-TCE": dict(id="APP-2026-00264", app_type="EOA", submitted="2026-04-16T08:32:00",
                     approved=[("B.Tech Computer Science and Engineering", "UG", 180),
                               ("B.Tech Electronics and Communication Engineering", "UG", 120)],
                     requested=None, fire_till="2026-05-31", nba_till="2028-06-30"),
    "INST-SIT": dict(id="APP-2026-00301", app_type="EOA", submitted=None,
                     approved=[("B.Tech Computer Science and Engineering", "UG", 120), ("B.Tech Civil Engineering", "UG", 60)],
                     requested=None, fire_till="2027-03-31",
                     only=["LAND_DEED", "BUILDING_COMPLETION", "FIRE_NOC", "AFFILIATION_LETTER", "TER_RECEIPT", "LAB_PHOTO:1"]),
}

FIRST = ["Aarti", "Rohan", "Sneha", "Vikram", "Priya", "Arjun", "Kavya", "Siddharth", "Neha", "Rahul", "Divya", "Karan",
         "Meera", "Aditya", "Pooja", "Nikhil", "Ananya", "Manish", "Shreya", "Varun", "Ishita", "Harsh", "Ritu", "Amit"]
LAST = ["Sharma", "Patil", "Iyer", "Reddy", "Nair", "Joshi", "Kulkarni", "Gupta", "Menon", "Rao", "Deshpande", "Verma",
        "Pillai", "Chauhan", "Bhat", "Saxena", "Mishra", "Kaur", "Das", "Hegde"]
DESIGNATIONS = [("Professor", "Ph.D."), ("Associate Professor", "Ph.D."), ("Assistant Professor", "M.Tech"),
                ("Assistant Professor", "M.E."), ("Assistant Professor", "Ph.D.")]
