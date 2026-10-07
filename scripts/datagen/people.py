import random

from .reference import COST_CENTRES, DIRECTOR_GROUPS, VP_FUNCTIONS, APPROVAL_LIMITS

FIRST = ["Aaron", "Adaeze", "Aisha", "Alan", "Alejandro", "Amara", "Amit", "Ana", "Andrea", "Anil", "Ben",
         "Bianca", "Caleb", "Camila", "Carlos", "Chen", "Chloe", "Chris", "Clara", "Daniel", "Deepa", "Derek",
         "Dmitri", "Eamon", "Elena", "Emeka", "Emma", "Ethan", "Fatima", "Felix", "Fiona", "Gabriel", "Gita",
         "Hamid", "Hana", "Henrik", "Ian", "Ines", "Isaac", "Ivy", "Jamal", "James", "Jasmine", "Jin", "Joel",
         "Jonas", "Karan", "Katarina", "Keiko", "Laila", "Laura", "Leon", "Lina", "Lucas", "Mahesh", "Maria",
         "Mateo", "Maya", "Mei", "Michael", "Mina", "Mohan", "Naomi", "Nathan", "Neha", "Nikhil", "Nora",
         "Oliver", "Olu", "Omar", "Paolo", "Pooja", "Quentin", "Rachel", "Rahul", "Ravi", "Rebecca", "Rhys",
         "Rosa", "Ruth", "Sam", "Sana", "Sean", "Shreya", "Simon", "Sinead", "Sophie", "Stefan", "Tariq",
         "Tessa", "Theo", "Tobias", "Uma", "Victor", "Vikram", "Wen", "Will", "Yara", "Yusuf", "Zoe"]
LAST = ["Abara", "Adeyemi", "Albrecht", "Alvarez", "Anand", "Bakker", "Banerjee", "Barros", "Becker", "Bhatt",
        "Blake", "Brennan", "Calloway", "Campos", "Castillo", "Chandra", "Choi", "Collins", "Costa", "Dalton",
        "Das", "Delgado", "Desai", "Doyle", "Duarte", "Eriksen", "Farrell", "Fischer", "Fontaine", "Gallagher",
        "Garcia", "Ghosh", "Gomez", "Gupta", "Hale", "Hansen", "Hayes", "Holm", "Hughes", "Ibarra", "Iyer",
        "Jensen", "Joshi", "Kaur", "Keller", "Khan", "Kim", "Kowalski", "Kulkarni", "Larsen", "Lewis", "Lin",
        "Lopez", "Maddox", "Malik", "Martens", "Mendes", "Mishra", "Morales", "Murphy", "Nakamura", "Novak",
        "Nunez", "O'Brien", "Okoye", "Olsen", "Pacheco", "Park", "Patel", "Pereira", "Pillai", "Quinn", "Rao",
        "Reddy", "Reyes", "Richter", "Rossi", "Saito", "Santos", "Schmidt", "Sen", "Shah", "Silva", "Singh",
        "Sorensen", "Sullivan", "Tan", "Thakur", "Torres", "Vargas", "Verma", "Vogel", "Walsh", "Wang",
        "Weber", "Yadav", "Young", "Zhang", "Zimmer"]

DOMAIN = "gbsc-demo.example"

# Named people the storyboard depends on. Everyone is fictional.
FIXED = [
    {"id": "E20417", "name": "Diana Moreno", "title": "Director, Finance GBSC", "level": "Director",
     "director_group": "Finance GBSC", "cost_centre": "CC7100"},
    {"id": "E10022", "name": "Grace Okafor", "title": "VP, Finance Operations", "level": "VP",
     "function": "Finance", "cost_centre": "CC7100"},
    {"id": "E31188", "name": "Julia Ortiz", "title": "Senior Counsel, Commercial", "level": "Staff",
     "cost_centre": "CC5100"},
    {"id": "E30542", "name": "Marcus Feld", "title": "Legal Operations Manager", "level": "Manager",
     "cost_centre": "CC5110", "specialist_role": "legal_ops", "owner_of": "CC5110"},
    {"id": "E20388", "name": "Hannah Leclerc", "title": "Director, Legal", "level": "Director",
     "director_group": "Legal", "cost_centre": "CC5100"},
    {"id": "E33901", "name": "Kevin Brandt", "title": "End-User Computing Lead", "level": "Staff",
     "cost_centre": "CC4410"},
    {"id": "E30911", "name": "Sofia Lindgren", "title": "IT Procurement Lead", "level": "Manager",
     "cost_centre": "CC7180", "specialist_role": "it_procurement"},
    {"id": "E30876", "name": "Arjun Mehta", "title": "Fixed Asset Accounting Lead", "level": "Manager",
     "cost_centre": "CC7150", "specialist_role": "fixed_assets"},
    {"id": "E30655", "name": "Nadia Petrova", "title": "Vendor Master Data Lead", "level": "Manager",
     "cost_centre": "CC7110", "specialist_role": "vendor_master"},
    {"id": "E34120", "name": "Alex Rivera", "title": "AP Specialist, Non-PO Invoices", "level": "Staff",
     "cost_centre": "CC7110", "specialist_role": "ap_reviewer"},
    {"id": "E30233", "name": "Samuel Whitaker", "title": "Assistant Controller", "level": "Manager",
     "cost_centre": "CC7150", "specialist_role": "controller"},
    {"id": "E30719", "name": "Priya Nair", "title": "Cash Application Lead", "level": "Manager",
     "cost_centre": "CC7170", "specialist_role": "cash_app"},
    {"id": "E10001", "name": "Robert Lindqvist", "title": "Chief Financial Officer", "level": "SVP",
     "cost_centre": "CC9900"},
    {"id": "E10002", "name": "Helena Marsh", "title": "SVP, GBSC Finance", "level": "SVP",
     "cost_centre": "CC7100"},
]


def _email(name: str) -> str:
    first, *rest = name.lower().replace("'", "").split(" ")
    return f"{first}.{''.join(rest)}@{DOMAIN}"


def build_people(rng: random.Random):
    cc_index = {c[0]: c for c in COST_CENTRES}
    used = {p["name"] for p in FIXED}
    next_id = iter(range(5001, 9999))

    def new_name():
        while True:
            n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used:
                used.add(n)
                return n

    people = []

    def add(pid, name, title, level, cc, **extra):
        code, cc_name, entity, function = cc_index[cc]
        p = {"id": pid, "name": name, "title": title, "level": level, "cost_centre": cc,
             "entity": entity, "function": function, "email": _email(name),
             "approval_limit": APPROVAL_LIMITS.get(level), "manager_id": None, "delegate_id": None,
             "out_of_office": None, "specialist_role": extra.get("specialist_role")}
        people.append(p)
        return p

    fixed_by_group = {f["director_group"]: f for f in FIXED if f.get("director_group")}
    fixed_by_fn = {f["function"]: f for f in FIXED if f.get("function")}
    fixed_owner = {f["owner_of"]: f for f in FIXED if f.get("owner_of")}

    vps = {}
    for fn, title in VP_FUNCTIONS.items():
        cc = next(c[0] for c in COST_CENTRES if c[3] == fn)
        if fn in fixed_by_fn:
            f = fixed_by_fn[fn]
            vps[fn] = add(f["id"], f["name"], f["title"], "VP", f["cost_centre"])
        else:
            vps[fn] = add(f"E1{next(next_id)}", new_name(), title, "VP", cc)

    directors = {}
    for group, ccs in DIRECTOR_GROUPS.items():
        if group in fixed_by_group:
            f = fixed_by_group[group]
            d = add(f["id"], f["name"], f["title"], "Director", f["cost_centre"])
        else:
            d = add(f"E2{next(next_id)}", new_name(), f"Director, {group}", "Director", ccs[0])
        d["manager_id"] = vps[d["function"]]["id"]
        for cc in ccs:
            directors[cc] = d

    owners = {}
    for code, cc_name, entity, fn in COST_CENTRES:
        if code in fixed_owner:
            f = fixed_owner[code]
            o = add(f["id"], f["name"], f["title"], "Manager", code, specialist_role=f.get("specialist_role"))
        else:
            o = add(f"E3{next(next_id)}", new_name(), f"Manager, {cc_name}", "Manager", code)
        o["manager_id"] = directors[code]["id"]
        owners[code] = o

    for f in FIXED:
        if any(p["id"] == f["id"] for p in people):
            continue
        p = add(f["id"], f["name"], f["title"], f["level"], f["cost_centre"],
                specialist_role=f.get("specialist_role"))
        if f["level"] in ("Staff", "Manager"):
            p["manager_id"] = owners[f["cost_centre"]]["id"] if f["level"] == "Staff" else directors[f["cost_centre"]]["id"]

    staff_titles = ["Analyst", "Senior Analyst", "Specialist", "Programme Manager", "Lead", "Coordinator"]
    requesters = {}
    for code, cc_name, entity, fn in COST_CENTRES:
        rs = [p for p in people if p["cost_centre"] == code and p["level"] == "Staff"]
        while len(rs) < 2:
            s = add(f"E3{next(next_id)}", new_name(), f"{rng.choice(staff_titles)}, {cc_name}", "Staff", code)
            s["manager_id"] = owners[code]["id"]
            rs.append(s)
        requesters[code] = [r["id"] for r in rs] + [owners[code]["id"]]

    # Delegates: each director delegates to a peer director in the same function where one exists.
    for d in {id(x): x for x in directors.values()}.values():
        peers = [x for x in {id(y): y for y in directors.values()}.values()
                 if x["function"] == d["function"] and x["id"] != d["id"]]
        d["delegate_id"] = peers[0]["id"] if peers else vps[d["function"]]["id"]
    for o in owners.values():
        o["delegate_id"] = directors[o["cost_centre"]]["id"]

    by_id = {p["id"]: p for p in people}
    cost_centres = []
    for code, cc_name, entity, fn in COST_CENTRES:
        cost_centres.append({"code": code, "name": cc_name, "entity": entity, "function": fn,
                             "owner_id": owners[code]["id"], "director_id": directors[code]["id"],
                             "vp_id": vps[fn]["id"], "requester_ids": requesters[code]})
    return people, cost_centres, by_id
