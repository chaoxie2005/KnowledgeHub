/**
 * 知文汇前端视觉升级脚本
 * 依赖：jQuery（已有）, Typed.js（CDN 引入）
 */
document.addEventListener('DOMContentLoaded', function () {

  // ========== 1. 导航栏滚动阴影 ==========
  const header = document.querySelector('.blog-header');
  if (header) {
    const handleScroll = function () {
      if (window.scrollY > 10) {
        header.classList.add('scrolled');
      } else {
        header.classList.remove('scrolled');
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
  }

  // ========== 2. Hero 打字机动画 ==========
  var titles = [
    '用代码记录思考',
    '让知识在分享中生长',
    '汇聚每一个技术人的洞见',
    '从学习到创造，一步之遥'
  ];
  var subtitles = [
    '每一篇文章，都是一次思维的沉淀',
    '不只是笔记，是成长的轨迹',
    '在这里，遇见更好的技术世界',
    '知文汇——属于开发者的知识花园'
  ];

  var idx = Math.floor(Math.random() * titles.length);
  var currentTitle = titles[idx];
  var currentSubtitle = subtitles[idx];

  var titleEl = document.getElementById('hero-title');
  var subtitleEl = document.getElementById('hero-subtitle');
  var sloganEl = document.getElementById('hero-slogan');

  if (titleEl && typeof Typed !== 'undefined') {
    new Typed('#hero-title', {
      strings: [currentTitle],
      typeSpeed: 80,
      showCursor: true,
      cursorChar: '|',
      onComplete: function () {
        if (subtitleEl) {
          new Typed('#hero-subtitle', {
            strings: [currentSubtitle],
            typeSpeed: 55,
            startDelay: 400,
            showCursor: true,
            cursorChar: '|'
          });
        }
      }
    });

    if (sloganEl) {
      setTimeout(function () {
        sloganEl.style.opacity = '1';
        sloganEl.style.transform = 'translateY(0)';
      }, 2500);
    }

    // 每 8 秒循环切换
    setInterval(function () {
      idx = (idx + 1) % titles.length;
      titleEl.innerHTML = '';
      subtitleEl.innerHTML = '';
      if (sloganEl) {
        sloganEl.style.opacity = '0';
        sloganEl.style.transform = 'translateY(10px)';
      }

      new Typed('#hero-title', {
        strings: [titles[idx]],
        typeSpeed: 80,
        showCursor: true,
        cursorChar: '|',
        onComplete: function () {
          if (subtitleEl) {
            new Typed('#hero-subtitle', {
              strings: [subtitles[idx]],
              typeSpeed: 55,
              startDelay: 400,
              showCursor: true,
              cursorChar: '|'
            });
          }
        }
      });

      setTimeout(function () {
        if (sloganEl) {
          sloganEl.style.opacity = '1';
          sloganEl.style.transform = 'translateY(0)';
        }
      }, 2500);
    }, 8000);
  }

  // ========== 3. 文章卡片滚动入场动画 ==========
  var cards = document.querySelectorAll('.article-card');
  if (cards.length > 0 && 'IntersectionObserver' in window) {
    var cardObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var index = Array.from(cards).indexOf(entry.target);
          entry.target.style.animationDelay = (index * 0.08) + 's';
          entry.target.classList.add('card-visible');
          cardObserver.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.15,
      rootMargin: '0px 0px -30px 0px'
    });

    cards.forEach(function (card) {
      card.classList.add('card-enter');
      cardObserver.observe(card);
    });
  } else if (cards.length > 0) {
    cards.forEach(function (card) { card.classList.add('card-visible'); });
  }

  // ========== 4. Hero 平滑滚动 ==========
  var heroCta = document.getElementById('hero-cta');
  var scrollIndicator = document.getElementById('hero-scroll-indicator');
  var articleGrid = document.querySelector('.article-grid');

  function scrollToArticles(e) {
    if (articleGrid) {
      e.preventDefault();
      articleGrid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  if (heroCta) {
    heroCta.addEventListener('click', scrollToArticles);
  }
  if (scrollIndicator) {
    scrollIndicator.addEventListener('click', function () {
      if (articleGrid) {
        articleGrid.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  // ========== 5. Ctrl+K 聚焦搜索框 ==========
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      var searchInput = document.querySelector('input[name="keyword"]');
      if (searchInput) searchInput.focus();
    }
  });

});
