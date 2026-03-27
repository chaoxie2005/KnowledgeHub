from article.models import Comment
from django.db.models import Count

def run():
    comments = Comment.objects.annotate(actual_likes=Count('comment_likes'))
    for c in comments:
        c.like_count = c.actual_likes
        c.save(update_fields=['like_count'])
    print(f"Updated {len(comments)} comments.")

if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'extraordinaryblog.settings')
    django.setup()
    run()
