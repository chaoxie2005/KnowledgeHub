from django.db.models.signals import post_save, post_delete
from django.db.models import F
from django.dispatch import receiver

from article.models import Article
from users.models import UserProfile


@receiver(post_save, sender=Article)
def update_article_count_on_save(sender, instance, created, **kwargs):
    if created and instance.status == "published":
        UserProfile.objects.filter(user=instance.author).update(
            article_count=F("article_count") + 1
        )
    elif not created:
        _recalc_article_count(instance.author)


@receiver(post_delete, sender=Article)
def update_article_count_on_delete(sender, instance, **kwargs):
    if instance.status == "published":
        UserProfile.objects.filter(user=instance.author).update(
            article_count=F("article_count") - 1
        )


def _recalc_article_count(user):
    count = Article.objects.filter(author=user, status="published").count()
    UserProfile.objects.filter(user=user).update(article_count=count)
