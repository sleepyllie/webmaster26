/**
 * North Alabama Community Resource Hub — app.js
 */

$(document).ready(function() {

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------
    let currentPage = 0;
    let currentQuery = '';
    let currentCategory = '';
    let allResources = [];
    let cardIndex = 0;

    // -------------------------------------------------------------------------
    // Sparkles
    // -------------------------------------------------------------------------
    const sparkleColors = ['#3b82f6','#60a5fa','#93c5fd','#ffffff'];
    let sparkleCount = 0;
    const MAX_SPARKLES = 30;
    let lastScrollY = 0;
    let scrollSparkleThrottle = 0;

    function createSparkle(x, y, isScroll) {
        if (sparkleCount >= MAX_SPARKLES) return;
        const vw = window.innerWidth, vh = window.innerHeight, m = 20;
        if (x < m || x > vw - m || y < m || y > vh - m) return;
        sparkleCount++;
        const color = sparkleColors[Math.floor(Math.random() * sparkleColors.length)];
        const size = isScroll ? (2 + Math.random() * 3) : (3 + Math.random() * 4);
        const dur  = 400 + Math.random() * 300;
        const $dot = $('<div class="sparkle-dot"></div>').css({
            position:'fixed', left:x+'px', top:y+'px',
            width:size+'px', height:size+'px', backgroundColor:color,
            borderRadius:'50%', pointerEvents:'none', zIndex:99998,
            opacity:1, transform:'scale(1)',
            transition:`opacity ${dur}ms ease-out, transform ${dur}ms ease-out`
        });
        $('body').append($dot);
        requestAnimationFrame(() => $dot.css({ opacity:0, transform:`scale(0.3) translateY(${isScroll?-15:-20}px)` }));
        setTimeout(() => { $dot.remove(); sparkleCount--; }, dur + 50);
    }

    function createScrollSparkles() {
        const delta = Math.abs(window.scrollY - lastScrollY);
        if (delta > 5) {
            scrollSparkleThrottle++;
            if (scrollSparkleThrottle % 3 === 0) {
                const vw = window.innerWidth, vh = window.innerHeight;
                createSparkle(50 + Math.random()*(vw-100), 50 + Math.random()*(vh-100), true);
                if (Math.random() > 0.6)
                    setTimeout(() => createSparkle(50+Math.random()*(vw-100), 50+Math.random()*(vh-100), true), 50);
            }
        }
        lastScrollY = window.scrollY;
    }

    // -------------------------------------------------------------------------
    // Cursor Glow
    // -------------------------------------------------------------------------
    let mouseX=0, mouseY=0, glowX=0, glowY=0, cst=0;
    const $cursorGlow = $('<div class="cursor-glow"></div>');

    if (window.innerWidth > 768) {
        $('body').append($cursorGlow);
        $cursorGlow.addClass('active');
        $(document).on('mousemove', function(e) {
            mouseX = e.clientX; mouseY = e.clientY;
            if (++cst % 8 === 0) createSparkle(mouseX, mouseY, false);
        });
        (function animateGlow() {
            glowX += (mouseX-glowX)*0.12; glowY += (mouseY-glowY)*0.12;
            $cursorGlow.css({ left:glowX, top:glowY });
            requestAnimationFrame(animateGlow);
        })();
        $(document).on('mouseenter','a,button,input,select,textarea,.resource-card,.spotlight-card,.stat-card', function() {
            $cursorGlow.addClass('hover');
            for(let i=0;i<3;i++) setTimeout(()=>createSparkle(mouseX+(Math.random()-.5)*30,mouseY+(Math.random()-.5)*30,false),i*40);
        });
        $(document).on('mouseleave','a,button,input,select,textarea,.resource-card,.spotlight-card,.stat-card', function() {
            $cursorGlow.removeClass('hover');
        });
        $(document).on('click', function(e) {
            for(let i=0;i<6;i++) setTimeout(()=>{
                const a=(i/6)*Math.PI*2, d=15+Math.random()*20;
                createSparkle(e.clientX+Math.cos(a)*d, e.clientY+Math.sin(a)*d, false);
            },i*25);
        });
    }

    // -------------------------------------------------------------------------
    // 3D Tilt
    // -------------------------------------------------------------------------
    if (window.innerWidth > 768) {
        $(document).on('mousemove','.spotlight-card,.stat-card', function(e) {
            const r=this.getBoundingClientRect();
            const rx=(e.clientY-r.top-r.height/2)/20, ry=(r.width/2-(e.clientX-r.left))/20;
            $(this).css({ transform:`perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-6px) scale(1.02)`, transition:'transform 0.1s ease' });
        });
        $(document).on('mouseleave','.spotlight-card,.stat-card', function() {
            $(this).css({ transform:'', transition:'transform 0.4s ease' });
        });
        $(document).on('mousemove','.btn', function(e) {
            const r=this.getBoundingClientRect();
            $(this).css({ transform:`translate(${(e.clientX-r.left-r.width/2)*0.15}px,${(e.clientY-r.top-r.height/2)*0.15}px)` });
        });
        $(document).on('mouseleave','.btn', function() { $(this).css({transform:''}); });
    }

    // -------------------------------------------------------------------------
    // Ripple
    // -------------------------------------------------------------------------
    $(document).on('click','.btn', function(e) {
        const r=this.getBoundingClientRect();
        const $rip=$('<span class="ripple"></span>').css({left:e.clientX-r.left,top:e.clientY-r.top});
        $(this).append($rip);
        setTimeout(()=>$rip.remove(), 600);
    });

    // -------------------------------------------------------------------------
    // Header scroll
    // -------------------------------------------------------------------------
    $(window).on('scroll', function() {
        $('.header').toggleClass('scrolled', $(window).scrollTop() > 50);
    });

    // -------------------------------------------------------------------------
    // Scroll reveal
    // -------------------------------------------------------------------------
    let ticking = false;
    function revealOnScroll() {
        const wb = $(window).scrollTop() + $(window).height();
        $('.reveal:not(.active)').each(function(i) {
            if ($(this).offset().top < wb-50) { $(this).css('transition-delay',Math.min(i*.08,.4)+'s').addClass('active'); }
        });
        $('.spotlight-card:not(.active)').each(function(i) {
            if ($(this).offset().top < wb-40) { const d=i*.15; $(this).css({'transition-delay':d+'s','--card-index':i}); setTimeout(()=>$(this).addClass('active'),d*1000); }
        });
        $('.about-stats .stat-card:not(.active)').each(function(i) {
            if ($(this).offset().top < wb-40) { const d=i*.15; $(this).css('transition-delay',d+'s'); setTimeout(()=>$(this).addClass('active'),d*1000); }
        });
        $('.resource-card:not(.active)').each(function(i) {
            if ($(this).offset().top < wb-30) { $(this).css('transition-delay',Math.min(i*.06,.4)+'s').addClass('active'); }
        });
        $('.submit-form:not(.active)').each(function() { if ($(this).offset().top < wb-60) $(this).addClass('active'); });
        $('.section-title:not(.active),.section-label:not(.active),.section-subtitle:not(.active)').each(function() {
            if ($(this).offset().top < wb-50) $(this).addClass('active');
        });
    }

    $(window).on('scroll', function() {
        createScrollSparkles();
        if (!ticking) { requestAnimationFrame(()=>{ revealOnScroll(); ticking=false; }); ticking=true; }
    });
    revealOnScroll(); setTimeout(revealOnScroll,200); setTimeout(revealOnScroll,500);

    // -------------------------------------------------------------------------
    // Hero parallax + fade
    // -------------------------------------------------------------------------
    $(window).on('scroll', function() {
        const s=$(window).scrollTop(), hh=$('.hero').outerHeight(), fs=100, fe=hh*.5;
        if (window.innerWidth>768 && s<hh)
            $('.hero-bg-image').css({transform:`scale(${1+s*.0002}) translateY(${s*.3}px)`});
        const $t=$('.hero-title'), $sub=$('.hero-subtitle'), $cta=$('.hero-cta');
        if (s < fs) {
            $t.add($sub).add($cta).removeClass('scroll-fade').addClass('scroll-visible');
        } else if (s < fe) {
            const p=(s-fs)/(fe-fs);
            $t.css({opacity:1-p,transform:`translateY(${-30*p}px) scale(${1-p*.05})`}).removeClass('scroll-fade scroll-visible');
            $sub.css({opacity:Math.max(0,1-p*1.2),transform:`translateY(${-35*p}px)`}).removeClass('scroll-fade scroll-visible');
            $cta.css({opacity:Math.max(0,1-p*1.4),transform:`translateY(${-40*p}px)`}).removeClass('scroll-fade scroll-visible');
        } else {
            $t.add($sub).add($cta).addClass('scroll-fade').removeClass('scroll-visible');
        }
    });

    // -------------------------------------------------------------------------
    // Counter
    // -------------------------------------------------------------------------
    function animateNumber($el, target, dur) {
        dur = dur||1500;
        const cur=parseInt($el.text())||0, t0=performance.now();
        function ease(t){return 1-Math.pow(1-t,4);}
        (function tick(now){
            const p=Math.min((now-t0)/dur,1);
            $el.text(Math.round(cur+(target-cur)*ease(p)));
            if(p<1) requestAnimationFrame(tick);
        })(t0);
    }

    // -------------------------------------------------------------------------
    // Init
    // -------------------------------------------------------------------------
    loadResources();
    setTimeout(()=>animateNumber($('#total-resources'),0), 600);

    // -------------------------------------------------------------------------
    // Event handlers
    // -------------------------------------------------------------------------
    $('#mobile-menu-btn').on('click', function() { $(this).toggleClass('active'); $('#nav').toggleClass('active'); });
    $('#nav a').on('click', function() { $('#mobile-menu-btn').removeClass('active'); $('#nav').removeClass('active'); });
    $('#search-btn').on('click', performSearch);
    $('#search-input').on('keypress', function(e) { if(e.which===13) performSearch(); });

    $('#category-filter').on('change', function() {
        currentCategory = $(this).val();
        currentPage = 0;
        loadResources();
    });

    $('#clear-filters').on('click', function() {
        $('#search-input').val(''); $('#category-filter').val('');
        currentQuery=''; currentCategory=''; currentPage=0;
        loadResources(); showToast('Filters cleared','info');
    });

    $('#load-more').on('click', function() { currentPage++; loadResources(true); });
    $('#submit-form').on('submit', function(e) { e.preventDefault(); submitResource(); });

    $('a[href^="#"]').on('click', function(e) {
        e.preventDefault();
        const $t=$($(this).attr('href'));
        if($t.length) $('html,body').animate({scrollTop:$t.offset().top-80},800);
    });

    $(document).on('keydown', function(e) {
        if(e.key==='Escape'){ $('#mobile-menu-btn').removeClass('active'); $('#nav').removeClass('active'); }
    });

    // -------------------------------------------------------------------------
    // Functions
    // -------------------------------------------------------------------------

    function performSearch() {
        currentQuery = $('#search-input').val().trim();
        currentPage = 0;
        loadResources();
    }

    function loadResources(append) {
        append = append || false;
        cardIndex = append ? allResources.length : 0;

        // FIX 1: send empty string on initial load — backend scopes to Alabama
        const params = {
            q: currentQuery || '',
            category: currentCategory,
            page: currentPage
        };

        if (!append) {
            $('#resource-container').html(
                '<div class="loading"><div class="loader"><div class="loader-dot"></div><div class="loader-dot"></div><div class="loader-dot"></div></div><p style="margin-top:16px;">Loading resources...</p></div>'
            );
        }

        $.ajax({
            url: '/api/resources', method: 'GET', data: params,
            success: function(response) {
                if (append) allResources = allResources.concat(response.resources);
                else        allResources = response.resources;

                renderResources(append);
                updateResultsCount(response.count);
                animateNumber($('#total-resources'), response.count, 1200);

                // FIX 2: geo-filter reduces results below 25 — use 20 as threshold
                $('#load-more').toggle(response.resources.length >= 20);

                // Notify user when showing fallback seed data
                if (response.source === 'fallback' && !append) {
                    showToast('Showing local directory — live data temporarily unavailable','info');
                }
            },
            error: function() {
                $('#resource-container').html('<p class="loading" style="color:#c53030;">Error loading resources. Please try again.</p>');
                showToast('Error loading resources','error');
            }
        });
    }

    function renderResources(append) {
        const $c = $('#resource-container');
        if (!append) $c.empty();
        if (allResources.length === 0) {
            $c.html('<p class="loading">No resources found. Try a different search term or category.</p>');
            return;
        }
        const start = append ? Math.max(0, allResources.length-25) : 0;
        const list  = append ? allResources.slice(start) : allResources;
        list.forEach((r,i) => $c.append(createResourceCard(r, cardIndex+i)));
        if (window.innerWidth>768) {
            $('.resource-card').off('mouseenter mouseleave')
                .on('mouseenter', ()=>$cursorGlow.addClass('hover'))
                .on('mouseleave', ()=>$cursorGlow.removeClass('hover'));
        }
    }

    function createResourceCard(resource, index) {
        const srcMap = {
            user:     ['user',     'Community'],
            pinned:   ['pinned',   'Featured'],
            seed:     ['seed',     'Local'],
            places:   ['places',   'Local Place'],
            nonprofit:['nonprofit','Nonprofit'],
            api:      ['api',      'Database'],
        };
        const [srcClass, srcLabel] = srcMap[resource.source] || ['api', 'Database'];
        const delay = (index%12)*0.05;
        let det='';
        if (resource.address) det += '<p><strong>Location:</strong> '+escapeHtml(resource.address)+'</p>';
        if (resource.phone)   det += '<p><strong>Phone:</strong> '   +escapeHtml(resource.phone)+'</p>';
        const web = resource.website ? '<p><a href="'+escapeHtml(resource.website)+'" target="_blank" rel="noopener">Visit Website &rarr;</a></p>' : '';
        return `
            <div class="resource-card" style="animation-delay:${delay}s">
                <h3>${escapeHtml(resource.name)}</h3>
                <span class="category-tag">${escapeHtml(resource.category)}</span>
                <p>${escapeHtml(resource.description)}</p>
                <div class="details">${det}${web}</div>
                <span class="source-badge ${srcClass}">${srcLabel}</span>
            </div>`;
    }

    function updateResultsCount(count) {
        // FIX 3: never show 'community' as a user-visible search term
        let text = count + ' resource'+(count!==1?'s':'')+' found';
        if (currentQuery)    text += ' for "'+currentQuery+'"';
        if (currentCategory) text += ' in '+currentCategory;
        $('#results-count').text(text);
    }

    function submitResource() {
        const $btn=$('#submit-form button[type="submit"]'), orig=$btn.text();
        $btn.prop('disabled',true).text('Submitting...');
        const fd = {
            name:        $('#resource-name').val().trim(),
            category:    $('#resource-category').val(),
            description: $('#resource-description').val().trim(),
            contact:     $('#resource-contact').val().trim(),
            address:     $('#resource-address').val().trim(),
            website:     $('#resource-website').val().trim()
        };
        if (!fd.name||!fd.category||!fd.description||!fd.contact) {
            showFormMessage('Please fill in all required fields.','error');
            $btn.prop('disabled',false).text(orig); return;
        }
        $.ajax({
            url:'/api/resources/submit', method:'POST',
            contentType:'application/json', data:JSON.stringify(fd),
            success: function(res) {
                if (res.ok) {
                    showFormMessage('Thank you! Your resource has been submitted successfully.','success');
                    showToast('Resource submitted!','success');
                    $('#submit-form')[0].reset();
                    if (window.innerWidth>768) {
                        const vw=window.innerWidth, vh=window.innerHeight;
                        for(let i=0;i<15;i++) setTimeout(()=>createSparkle(100+Math.random()*(vw-200),100+Math.random()*(vh-200),false),i*40);
                    }
                    setTimeout(()=>{ currentPage=0; loadResources(); },1500);
                } else {
                    showFormMessage(res.error||'Submission failed. Please try again.','error');
                }
                $btn.prop('disabled',false).text(orig);
            },
            error: function() {
                showFormMessage('An error occurred. Please try again later.','error');
                showToast('Submission failed','error');
                $btn.prop('disabled',false).text(orig);
            }
        });
    }

    function showFormMessage(msg, type) {
        const $m=$('#form-message').removeClass('success error').addClass(type).text(msg).show();
        $('html,body').animate({scrollTop:$m.offset().top-200},500);
        if(type==='success') setTimeout(()=>$m.fadeOut(400),5000);
    }

    function showToast(msg, type) {
        const $t=$('#toast').removeClass('success error info').addClass(type||'info');
        $('#toast-message').text(msg); $t.addClass('show');
        setTimeout(()=>$t.removeClass('show'),3500);
    }

    function escapeHtml(text) {
        if (!text) return '';
        const d=document.createElement('div'); d.textContent=text; return d.innerHTML;
    }

});
