import json
import os
import requests
from datetime import datetime

BUFFER_GRAPHQL = "https://api.buffer.com/graphql"

def read_data():
    with open("data.json", "r", encoding="utf-8") as f:
        return json.load(f)

def write_data(data):
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

def graphql(token, query, variables=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(BUFFER_GRAPHQL, headers=headers, json=payload)
    if r.status_code != 200:
        print(f"  ❌ HTTP {r.status_code}: {r.text[:200]}")
        return None
    resp = r.json()
    if "errors" in resp:
        print(f"  ❌ GraphQL errors: {resp['errors']}")
        return None
    return resp.get("data")

def get_channels(token):
    query = """
    query {
      channels {
        id
        name
        service
      }
    }
    """
    data = graphql(token, query)
    if not data:
        return []
    return data.get("channels", [])

def find_channel_id(channels, name_keyword):
    for ch in channels:
        if name_keyword.lower() in ch.get("name", "").lower():
            return ch["id"]
    return None

def create_post(token, channel_id, text):
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id dueAt }
        }
        ... on MutationError {
          message
        }
      }
    }
    """
    variables = {
        "input": {
            "text": text,
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": "publishNow"
        }
    }
    data = graphql(token, mutation, variables)
    if not data:
        return False
    result = data.get("createPost", {})
    if "message" in result:
        print(f"  ❌ Buffer erreur: {result['message']}")
        return False
    if result.get("post"):
        print(f"  ✅ Buffer: publié (id: {result['post']['id']})")
        return True
    return False

def main():
    buffer_token = os.environ.get("BUFFER_API_KEY", "")
    if not buffer_token:
        print("❌ BUFFER_API_KEY non configuré")
        return

    channels = get_channels(buffer_token)
    if not channels:
        print("❌ Impossible de récupérer les canaux Buffer")
        return

    print(f"✅ {len(channels)} canal/canaux Buffer trouvé(s):")
    for ch in channels:
        print(f"   - {ch.get('service')} : {ch.get('name','?')} (id: {ch.get('id')})")

    channel_map = {
        "li":     find_channel_id(channels, "sulabooks"),
        "li_dov": find_channel_id(channels, "dovozo"),
        "tt":     find_channel_id(channels, "sulabooks"),
    }
    print("Mapping réseaux :", channel_map)

    data = read_data()
    changed = False
    now_str = datetime.now().isoformat()

    for profile in ("influenceuse", "dovozo"):
        posts_by_date = data.get(profile, {}).get("posts", {})
        for date_str, posts_list in posts_by_date.items():
            for i, post in enumerate(posts_list):
                if post.get("status") != 1:
                    continue
                if not is_due(date_str, post.get("time", "")):
                    continue
                network = post.get("network", "")
                channel_id = channel_map.get(network)
                print(f"\n📤 [{profile}] {date_str} — {post.get('title','?')} ({network})")
                if not channel_id:
                    print(f"  ⚠️  Réseau '{network}' non trouvé dans Buffer — ignoré")
                    continue
                parts = [p for p in [post.get("title"), post.get("desc"), post.get("tags")] if p]
                text = "\n\n".join(parts)[:3000]
                success = create_post(buffer_token, channel_id, text)
                if success:
                    data[profile]["posts"][date_str][i]["status"] = 2
                    data[profile]["posts"][date_str][i]["publishedAt"] = now_str
                    changed = True

    if changed:
        write_data(data)
        print("\n✅ data.json mis à jour")
    else:
        print("\nℹ️  Aucun post à publier pour l'instant")

if __name__ == "__main__":
    main()
