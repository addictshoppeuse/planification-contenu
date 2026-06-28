"""
Auto-publication des posts via Buffer API.
Lit data.json, publie les posts status=1 dont l'heure est passée,
met à jour le statut à 2 (publié).
"""
import json
import os
import base64
import requests
from datetime import datetime

BUFFER_API = "https://api.bufferapp.com/1"


# ── Lecture / écriture data.json ──────────────────────────────────────────────

def read_data():
    with open("data.json", "r", encoding="utf-8") as f:
        return json.load(f)

def write_data(data):
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Vérification heure de publication ─────────────────────────────────────────

def is_due(date_str, time_str):
    now = datetime.now()
    try:
        if time_str:
            scheduled = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        else:
            scheduled = datetime.strptime(date_str, "%Y-%m-%d")
        return now >= scheduled
    except Exception:
        return True


# ── Buffer : récupérer les profils connectés ──────────────────────────────────

def get_buffer_profiles(token):
    r = requests.get(
        f"{BUFFER_API}/profiles.json",
        headers={"Authorization": f"Bearer {token}"}
    )
    if r.status_code != 200:
        print(f"  ❌ Buffer profiles erreur {r.status_code}: {r.text[:200]}")
        return []
    return r.json()


def find_profile_id(profiles, service, is_company=False):
    """Trouve l'ID Buffer pour un réseau donné (linkedin perso, linkedin company, tiktok)."""
    for p in profiles:
        svc = p.get("service", "").lower()
        if service == "linkedin":
            if svc == "linkedin":
                if is_company and p.get("service_type") == "page":
                    return p["id"]
                if not is_company and p.get("service_type") != "page":
                    return p["id"]
        elif service == "tiktok" and svc == "tiktok":
            return p["id"]
    return None


# ── Buffer : publier un post ──────────────────────────────────────────────────

def post_to_buffer(post, profile_id, token):
    parts = [p for p in [post.get("title"), post.get("desc"), post.get("tags")] if p]
    text = "\n\n".join(parts)[:3000]

    data = {
        "profile_ids[]": profile_id,
        "text": text,
        "now": "true",
    }

    # Ajouter image si disponible (base64 → upload GitHub déjà fait côté app)
    # Ici on gère les images stockées en base64 dans data.json
    images = post.get("images", [])
    if images and images[0]:
        img_b64 = images[0]
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]
        # Uploader l'image sur Buffer
        img_bytes = base64.b64decode(img_b64)
        upload_r = requests.post(
            f"{BUFFER_API}/media/upload.json",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("image.jpg", img_bytes, "image/jpeg")}
        )
        if upload_r.status_code == 200:
            media_id = upload_r.json().get("id")
            if media_id:
                data["media[photo]"] = media_id

    r = requests.post(
        f"{BUFFER_API}/updates/create.json",
        headers={"Authorization": f"Bearer {token}"},
        data=data
    )
    if r.status_code == 200:
        resp = r.json()
        if resp.get("success"):
            print(f"  ✅ Buffer : publié '{post.get('title', '?')}'")
            return True
        else:
            print(f"  ❌ Buffer erreur : {resp}")
            return False
    else:
        print(f"  ❌ Buffer HTTP {r.status_code} : {r.text[:300]}")
        return False


# ── Boucle principale ─────────────────────────────────────────────────────────

def main():
    buffer_token = os.environ.get("BUFFER_API_KEY", "")

    if not buffer_token:
        print("❌ BUFFER_API_KEY non configuré")
        return

    # Récupérer les profils Buffer une seule fois
    profiles = get_buffer_profiles(buffer_token)
    if not profiles:
        print("❌ Impossible de récupérer les profils Buffer")
        return

    print(f"✅ {len(profiles)} profil(s) Buffer trouvé(s) :")
    for p in profiles:
        print(f"   - {p.get('service')} / {p.get('service_type','?')} : {p.get('formatted_username','?')} (id: {p.get('id')})")

    data = read_data()
    changed = False
    now_str = datetime.now().isoformat()

    # Mapping réseau → profil Buffer
    # li = LinkedIn perso, li_dov = LinkedIn Dovozo (company page), tt = TikTok
    profile_map = {
        "li":     find_profile_id(profiles, "linkedin", is_company=False),
        "li_dov": find_profile_id(profiles, "linkedin", is_company=True),
        "tt":     find_profile_id(profiles, "tiktok"),
    }
    print("Mapping réseaux :", profile_map)

    for profile in ("influenceuse", "dovozo"):
        posts_by_date = data.get(profile, {}).get("posts", {})

        for date_str, posts_list in posts_by_date.items():
            for i, post in enumerate(posts_list):
                if post.get("status") != 1:
                    continue
                if not is_due(date_str, post.get("time", "")):
                    continue

                network = post.get("network", "")
                buffer_profile_id = profile_map.get(network)

                print(f"\n📤 [{profile}] {date_str} — {post.get('title','?')} ({network})")

                if not buffer_profile_id:
                    print(f"  ⚠️  Réseau '{network}' non trouvé dans Buffer — ignoré")
                    continue

                success = post_to_buffer(post, buffer_profile_id, buffer_token)

                if success:
                    data[profile]["posts"][date_str][i]["status"] = 2
                    data[profile]["posts"][date_str][i]["publishedAt"] = now_str
                    changed = True

    if changed:
        write_data(data)
        print("\n✅ data.json mis à jour avec les nouveaux statuts")
    else:
        print("\nℹ️  Aucun post à publier pour l'instant")


if __name__ == "__main__":
    main()
