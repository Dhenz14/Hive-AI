import logging
import requests
import hashlib
from hiveai.config import HIVE_API_NODES, HIVE_PRIMARY_TAG, HIVE_REFINED_TAG
from hiveai.models import SessionLocal, HiveKnown, Job

logger = logging.getLogger(__name__)


def hive_api_call(method, params, timeout=15):
    for node in HIVE_API_NODES:
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1,
            }
            resp = requests.post(node, json=payload, timeout=timeout)
            data = resp.json()
            if "result" in data:
                return data["result"]
            if "error" in data:
                logger.warning(f"Hive API error from {node}: {data['error']}")
                continue
        except Exception as e:
            logger.warning(f"Hive node {node} failed: {e}")
            continue
    raise Exception("All Hive API nodes failed")


def search_by_tag(tag, limit=20):
    results = []
    try:
        posts = hive_api_call(
            "condenser_api.get_discussions_by_created",
            [{"tag": tag, "limit": min(limit, 20)}]
        )
        if posts:
            results.extend(posts)
    except Exception as e:
        logger.error(f"Tag search failed for {tag}: {e}")
    return results


def search_topic_on_hive(topic, job_id):
    db = SessionLocal()
    try:
        found_posts = []

        archive_posts = search_by_tag(HIVE_PRIMARY_TAG, limit=100)
        refined_posts = search_by_tag(HIVE_REFINED_TAG, limit=100)
        all_posts = archive_posts + refined_posts

        topic_lower = topic.lower()
        topic_words = set(topic_lower.split())

        for post in all_posts:
            title = (post.get("title", "") or "").lower()
            body = (post.get("body", "") or "").lower()[:2000]
            tags = post.get("json_metadata", {})
            if isinstance(tags, str):
                import json
                try:
                    tags = json.loads(tags)
                except:
                    tags = {}
            post_tags = [t.lower() for t in tags.get("tags", [])]

            relevance = 0
            for word in topic_words:
                if len(word) < 3:
                    continue
                if word in title:
                    relevance += 3
                if word in body:
                    relevance += 1
                if any(word in t for t in post_tags):
                    relevance += 2

            if relevance >= 2:
                url = f"https://hive.blog/@{post.get('author', '')}/{post.get('permlink', '')}"
                content_hash = hashlib.sha256(
                    (post.get("body", "") or "").encode()
                ).hexdigest()

                known = HiveKnown(
                    job_id=job_id,
                    url=url,
                    permlink=post.get("permlink", ""),
                    author=post.get("author", ""),
                    title=post.get("title", ""),
                    content_hash=content_hash,
                    tags=post_tags,
                )
                db.add(known)
                found_posts.append({
                    "url": url,
                    "title": post.get("title", ""),
                    "author": post.get("author", ""),
                    "content_hash": content_hash,
                    "body": post.get("body", ""),
                })

        job = db.get(Job, job_id)
        if job:
            job.hive_ping_count = len(found_posts)
            job.status = "hive_pinged"
        db.commit()

        logger.info(f"Hive ping for '{topic}': found {len(found_posts)} relevant posts")
        return found_posts

    except Exception as e:
        logger.error(f"Hive ping failed for topic '{topic}': {e}")
        job = db.get(Job, job_id)
        if job:
            job.status = "hive_pinged"
            job.hive_ping_count = 0
        db.commit()
        return []
    finally:
        db.close()


def get_exclusion_urls(job_id):
    db = SessionLocal()
    try:
        known = db.query(HiveKnown).filter(HiveKnown.job_id == job_id).all()
        return [k.url for k in known]
    finally:
        db.close()
