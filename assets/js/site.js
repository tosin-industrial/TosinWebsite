/*
 * 騰信工業官網互動程式（取代原本的 jQuery、Elementor 前端程式與 Blocksy main.js）
 *
 * 1. 側邊選單（手機版）與搜尋視窗的開關
 * 2. 手機選單的子選單展開
 * 3. 桌機選單的下拉選單（滑鼠移入、鍵盤 Tab）
 * 4. 回到頂端按鈕
 * 5. Elementor 進場動畫（捲到才淡入）
 * 6. 圖片輪播（Elementor 圖片輪播 → Swiper，只有首頁與設備頁載入 Swiper）
 */
(function () {
	'use strict';

	var doc = document;
	var body = doc.body;
	var isZh = (doc.documentElement.lang || '').toLowerCase().indexOf('zh') === 0;
	var TEXT = isZh
		? { expand: '展開下拉選單', collapse: '收合下拉選單' }
		: { expand: 'Expand dropdown menu', collapse: 'Collapse dropdown menu' };

	function each(selector, fn, root) {
		Array.prototype.forEach.call((root || doc).querySelectorAll(selector), fn);
	}

	/* ---------- 1. 側邊選單與搜尋視窗 ---------- */

	var openPanel = null;
	var lastTrigger = null;

	function panelMode(panel) {
		var b = panel.getAttribute('data-behaviour') || '';
		if (b.indexOf('right-side') > -1) return ':right';
		if (b.indexOf('left-side') > -1) return ':left';
		return '';
	}

	function showPanel(panel, trigger) {
		if (openPanel) hidePanel(openPanel, true);
		openPanel = panel;
		lastTrigger = trigger || null;
		var scrollbar = window.innerWidth - doc.documentElement.clientWidth;
		body.style.setProperty('--scrollbar-width', scrollbar + 'px');
		body.style.overflow = 'hidden';
		panel.removeAttribute('inert');
		panel.setAttribute('aria-modal', 'true');
		panel.classList.add('active');
		each('[data-toggle-panel="#' + panel.id + '"]', function (t) { t.setAttribute('aria-expanded', 'true'); });
		// 先設成 "in"，下一個畫格再加方向，讓 CSS 轉場動畫跑起來
		body.setAttribute('data-panel', 'in');
		requestAnimationFrame(function () {
			requestAnimationFrame(function () {
				if (openPanel === panel) body.setAttribute('data-panel', 'in' + panelMode(panel));
			});
		});
		var field = panel.querySelector('input[type="search"]');
		if (field) setTimeout(function () { field.focus(); }, 100);
	}

	function hidePanel(panel, instant) {
		if (!panel) return;
		openPanel = null;
		each('[data-toggle-panel="#' + panel.id + '"]', function (t) { t.setAttribute('aria-expanded', 'false'); });
		var finish = function () {
			if (openPanel) return;
			panel.classList.remove('active');
			panel.setAttribute('inert', '');
			panel.removeAttribute('aria-modal');
			body.removeAttribute('data-panel');
			body.style.overflow = '';
			body.style.removeProperty('--scrollbar-width');
		};
		if (instant) {
			panel.classList.remove('active');
			panel.setAttribute('inert', '');
			panel.removeAttribute('aria-modal');
			return;
		}
		body.setAttribute('data-panel', 'out' + panelMode(panel));
		setTimeout(finish, 250);
		if (lastTrigger) lastTrigger.focus({ preventScroll: true });
	}

	each('[data-toggle-panel]', function (trigger) {
		trigger.addEventListener('click', function (e) {
			e.preventDefault();
			var panel = doc.querySelector(trigger.getAttribute('data-toggle-panel'));
			if (!panel) return;
			if (openPanel === panel) hidePanel(panel); else showPanel(panel, trigger);
		});
	});

	each('.ct-panel', function (panel) {
		each('.ct-toggle-close', function (btn) {
			btn.addEventListener('click', function (e) {
				e.preventDefault();
				hidePanel(panel);
			});
		}, panel);
		// 點面板外的半透明背景就關閉
		panel.addEventListener('click', function (e) {
			var inner = panel.querySelector('.ct-panel-inner') || panel.querySelector('.ct-panel-content');
			if (e.target === panel || (inner && !inner.contains(e.target) && !panel.querySelector('.ct-panel-actions').contains(e.target))) {
				hidePanel(panel);
			}
		});
	});

	doc.addEventListener('keydown', function (e) {
		if ((e.key === 'Escape' || e.key === 'Esc') && openPanel) hidePanel(openPanel);
	});

	// 視窗放大到桌機寬度時，手機側選單自動關閉
	window.addEventListener('resize', function () {
		if (openPanel && openPanel.id === 'offcanvas' && window.innerWidth >= 1000) hidePanel(openPanel);
	});

	/* ---------- 2. 手機選單子選單 ---------- */

	each('.mobile-menu .ct-toggle-dropdown-mobile', function (btn) {
		btn.addEventListener('click', function (e) {
			e.preventDefault();
			var li = btn.closest('li');
			var open = li.classList.toggle('dropdown-active');
			btn.setAttribute('aria-expanded', open ? 'true' : 'false');
			btn.setAttribute('aria-label', open ? TEXT.collapse : TEXT.expand);
		});
	});

	/* ---------- 3. 桌機下拉選單 ---------- */

	each('nav[data-interaction="hover"]', function (nav) {
		nav.setAttribute('data-responsive', 'yes');
	});

	each('nav[data-interaction="hover"] .menu-item-has-children', function (li) {
		var ghost = li.querySelector(':scope > .ct-toggle-dropdown-desktop-ghost');
		var sub = li.querySelector(':scope > .sub-menu');

		function placeSubmenu() {
			// 子選單若會超出視窗右緣就改往左展開
			if (!sub) return;
			var rect = li.getBoundingClientRect();
			var width = sub.offsetWidth || 0;
			li.setAttribute('data-submenu', rect.left + width > doc.documentElement.clientWidth ? 'left' : 'right');
		}

		function setOpen(open) {
			li.classList.toggle('ct-active', open);
			if (ghost) {
				ghost.setAttribute('aria-expanded', open ? 'true' : 'false');
				ghost.setAttribute('aria-label', open ? TEXT.collapse : TEXT.expand);
			}
		}

		placeSubmenu();
		window.addEventListener('resize', placeSubmenu);
		li.addEventListener('mouseenter', function () { placeSubmenu(); setOpen(true); });
		li.addEventListener('mouseleave', function () { setOpen(false); });
		li.addEventListener('focusin', function () { setOpen(true); });
		li.addEventListener('focusout', function (e) {
			if (!li.contains(e.relatedTarget)) setOpen(false);
		});
		if (ghost) {
			ghost.addEventListener('click', function (e) {
				e.preventDefault();
				setOpen(!li.classList.contains('ct-active'));
			});
		}
	});

	/* ---------- 4. 回到頂端 ---------- */

	each('.ct-back-to-top', function (btn) {
		var update = function () {
			var show = window.scrollY > 300;
			if (show) btn.removeAttribute('hidden');
			btn.classList.toggle('ct-show', show);
		};
		window.addEventListener('scroll', update, { passive: true });
		update();
		btn.addEventListener('click', function (e) {
			e.preventDefault();
			window.scrollTo({ top: 0, behavior: 'smooth' });
		});
	});

	/* ---------- 5. Elementor 進場動畫 ---------- */

	function settingsOf(el) {
		try {
			return JSON.parse(el.getAttribute('data-settings') || '{}');
		} catch (err) {
			return {};
		}
	}

	var animated = [];
	each('[data-settings]', function (el) {
		var s = settingsOf(el);
		var name = s._animation || s.animation;
		if (!name || name === 'none') return;
		animated.push({ el: el, name: name, delay: +(s._animation_delay || s.animation_delay || 0) });
	});

	function reveal(item) {
		setTimeout(function () {
			item.el.classList.remove('elementor-invisible');
			item.el.classList.add('animated', item.name);
		}, item.delay);
	}

	if (animated.length && 'IntersectionObserver' in window &&
			!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) {
		// 只有確定 JS 能跑才先隱藏；捲到畫面內才淡入
		var observer = new IntersectionObserver(function (entries) {
			entries.forEach(function (entry) {
				if (!entry.isIntersecting) return;
				observer.unobserve(entry.target);
				animated.forEach(function (item) { if (item.el === entry.target) reveal(item); });
			});
		}, { rootMargin: '0px 0px -10% 0px' });
		animated.forEach(function (item) {
			item.el.classList.add('elementor-invisible');
			observer.observe(item.el);
		});
		// 保險：3 秒後仍未出現的（例如被擋在不會捲到的位置）一律顯示，絕不永遠隱形
		window.addEventListener('load', function () {
			setTimeout(function () {
				animated.forEach(function (item) {
					if (item.el.classList.contains('elementor-invisible') && item.el.getBoundingClientRect().top < window.innerHeight) reveal(item);
				});
			}, 3000);
		});
	}

	/* ---------- 6. 圖片輪播 ---------- */

	// Elementor 的斷點：手機 ≤767、平板 ≤1024
	var BREAKPOINTS = [['mobile', 767], ['tablet', 1024]];

	function responsive(s, key, device) {
		// Elementor 規則：某裝置沒設值就沿用較大裝置的值
		var order = ['mobile', 'tablet', ''];
		for (var i = order.indexOf(device || ''); i < order.length; i++) {
			var k = order[i] ? key + '_' + order[i] : key;
			var v = s[k];
			if (v && typeof v === 'object') v = v.size;
			if (v !== undefined && v !== null && v !== '') return +v;
		}
		return 0;
	}

	function carouselOptions(widget, s) {
		var slides = +s.slides_to_show || 3;
		var single = slides === 1;
		var opts = {
			slidesPerView: slides,
			loop: s.infinite === 'yes',
			speed: +s.speed || 500,
			breakpoints: {}
		};
		// Swiper 的斷點是「寬度 ≥」，換算方式同 Elementor：0 起算手機、767 起算平板、1024 起算桌機
		var mobile = { slidesPerView: +s.slides_to_show_mobile || 1, slidesPerGroup: +s.slides_to_scroll_mobile || 1 };
		var tablet = { slidesPerView: +s.slides_to_show_tablet || (single ? 1 : 2), slidesPerGroup: +s.slides_to_scroll_tablet || 1 };
		var desktop = { slidesPerView: slides, slidesPerGroup: single ? 1 : (+s.slides_to_scroll || 1) };
		if (s.image_spacing_custom) {
			mobile.spaceBetween = responsive(s, 'image_spacing_custom', 'mobile');
			tablet.spaceBetween = responsive(s, 'image_spacing_custom', 'tablet');
			desktop.spaceBetween = responsive(s, 'image_spacing_custom');
			opts.spaceBetween = desktop.spaceBetween;
		}
		opts.breakpoints[0] = mobile;
		opts.breakpoints[BREAKPOINTS[0][1]] = tablet;
		opts.breakpoints[BREAKPOINTS[1][1]] = desktop;
		if (s.autoplay === 'yes') {
			opts.autoplay = { delay: +s.autoplay_speed || 5000, disableOnInteraction: s.pause_on_interaction === 'yes' };
		}
		if (single) {
			opts.effect = s.effect || 'slide';
			if (opts.effect === 'fade') opts.fadeEffect = { crossFade: true };
		} else {
			opts.slidesPerGroup = +s.slides_to_scroll || 1;
		}
		var nav = s.navigation || '';
		if (nav === 'arrows' || nav === 'both') {
			opts.navigation = {
				prevEl: widget.querySelector('.elementor-swiper-button-prev'),
				nextEl: widget.querySelector('.elementor-swiper-button-next')
			};
		}
		if (nav === 'dots' || nav === 'both') {
			opts.pagination = {
				el: widget.querySelector('.swiper-pagination'),
				type: 'bullets',
				clickable: true,
				renderBullet: function (index, cls) {
					return '<span class="' + cls + '" role="button" tabindex="0" data-bullet-index="' + index + '" aria-label="Go to slide ' + (index + 1) + '"></span>';
				}
			};
		}
		opts.a11y = {
			enabled: true,
			prevSlideMessage: 'Previous slide',
			nextSlideMessage: 'Next slide',
			firstSlideMessage: 'This is the first slide',
			lastSlideMessage: 'This is the last slide'
		};
		// 使用者系統設定「減少動態效果」時不自動輪播（同 Elementor）
		if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			opts.speed = 0;
			opts.autoplay = false;
		}
		return opts;
	}

	if (window.Swiper) {
		each('.elementor-widget-image-carousel', function (widget) {
			var container = widget.querySelector('.elementor-image-carousel-wrapper');
			if (!container || container.querySelectorAll('.swiper-slide').length < 2) return;
			// Elementor 會加上這兩個 class，CSS 依此調整輪播外框寬度
			var wrap = widget.closest('.elementor-widget-wrap');
			if (wrap) wrap.classList.add('e-swiper-container');
			widget.classList.add('e-widget-swiper');
			var s = settingsOf(widget);
			var swiper = new window.Swiper(container, carouselOptions(widget, s));
			if (s.autoplay === 'yes' && s.pause_on_hover === 'yes' && swiper.autoplay) {
				container.addEventListener('mouseenter', function () { swiper.autoplay.stop(); });
				container.addEventListener('mouseleave', function () { swiper.autoplay.start(); });
			}
		});
	}
})();
