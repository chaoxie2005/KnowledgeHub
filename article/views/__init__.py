# Re-export all views for backward compatibility.
# All existing imports like `from article.views import detail` continue to work.
from .api import ArticleViewSet, CategoryViewSet, CommentViewSet
from .display import detail, category_list, tag_list, archive_list, download_markdown, download_PDF, upload_image
from .crud import publish_article, drafts, edit_draft, delete_draft, published, edit_published, delete_published
from .hot_pages import juejin_hot, csdn_hot
from .ai import ai_optimize_title, ai_generate_summary, article_ai_qa, global_ai_qa, clear_ai_history, generate_article_audio_view
from .comments import comment_like, delete_comment, comment_management
from .quiz import generate_article_quiz, submit_quiz_answer, wrong_question_book
from .study import create_or_get_study_plan, study_plan_checkin, learning_dashboard_stats
from .decorators import time_it
