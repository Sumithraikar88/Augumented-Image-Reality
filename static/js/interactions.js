/* VisionForge toon & motion layer: cursor fx, cartoon characters, reveals. */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(pointer: fine)").matches;
  const orbit = document.querySelector(".cursor-orbit");
  const spark = document.querySelector(".cursor-spark");
  const mascot = document.querySelector(".mascot-dock");
  const message = document.querySelector(".mascot-message");
  const buddy = document.querySelector(".toon-buddy");
  const buddyBubble = document.querySelector(".buddy-bubble");
  const sparklePool = ["✨", "⭐", "💫", "🎉", "🚀", "💜"];

  const mascotLines = [
    "Hi! Ready to make some AR magic?",
    "Point, click, and explore!",
    "Your vision lab is online!",
    "Image received. Let us enhance it!",
    "Tracking markers like a pro! 🎯",
    "Robots + OpenCV = best friends 🤖",
  ];

  const buddyLines = [
    "Bloop! I'm Blobby 💜",
    "Psst… try the cartoon filter!",
    "Wanna see a rocket fly?",
    "Fun fact: ORB never sleeps!",
    "Click anywhere — I love sparkles!",
  ];

  const sayTo = (node, text) => {
    if (!node) return;
    node.textContent = text;
  };

  if (!mascot || !buddy) return;

  /* ---------- mouse trail particles + animated custom cursor ---------- */
  if (finePointer && !reduceMotion && orbit && spark) {
    document.documentElement.classList.add("pointer-effects");
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let lastTrail = 0;
    let trailHue = 0;

    const follow = () => {
      currentX += (targetX - currentX) * 0.17;
      currentY += (targetY - currentY) * 0.17;
      orbit.style.transform = `translate3d(${currentX}px, ${currentY}px, 0)`;
      requestAnimationFrame(follow);
    };
    requestAnimationFrame(follow);

    const spawnTrail = (x, y) => {
      const particle = document.createElement("i");
      particle.className = "cursor-trail";
      const size = 5 + Math.random() * 7;
      const palette = ["#22d3ee", "#f472b6", "#a78bfa", "#fde047", "#34d399"];
      trailHue = (trailHue + 1) % palette.length;
      particle.style.width = `${size}px`;
      particle.style.height = `${size}px`;
      particle.style.left = `${x + (Math.random() * 14 - 7)}px`;
      particle.style.top = `${y + (Math.random() * 14 - 7)}px`;
      particle.style.background = palette[trailHue];
      particle.style.boxShadow = `0 0 10px ${palette[trailHue]}`;
      document.body.appendChild(particle);
      particle.addEventListener("animationend", () => particle.remove());
    };

    window.addEventListener("pointermove", (event) => {
      targetX = event.clientX;
      targetY = event.clientY;
      spark.style.transform = `translate3d(${targetX}px, ${targetY}px, 0)`;

      const now = performance.now();
      if (now - lastTrail > 45) {
        lastTrail = now;
        spawnTrail(event.clientX, event.clientY);
      }

      const target = event.target instanceof Element ? event.target : null;
      const hoverable = target?.closest("a, button, input, select, label, .feature-card, .thumb-card");
      orbit.classList.toggle("is-hovering", Boolean(hoverable));
      mascot.classList.toggle("is-watching", Boolean(hoverable));
    });

    /* click = ring + particle burst + emoji sparkle */
    window.addEventListener("click", (event) => {
      const pulse = document.createElement("i");
      pulse.className = "click-pulse";
      pulse.style.left = `${event.clientX}px`;
      pulse.style.top = `${event.clientY}px`;
      document.body.appendChild(pulse);
      pulse.addEventListener("animationend", () => pulse.remove());

      const burst = document.createElement("div");
      burst.className = "click-burst";
      burst.style.left = `${event.clientX}px`;
      burst.style.top = `${event.clientY}px`;
      const palette = ["#22d3ee", "#f472b6", "#a78bfa", "#fde047", "#34d399"];
      for (let i = 0; i < 10; i += 1) {
        const ray = document.createElement("i");
        const angle = (Math.PI * 2 * i) / 10 + Math.random() * 0.5;
        const distance = 26 + Math.random() * 30;
        ray.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
        ray.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
        ray.style.setProperty("--c", palette[i % palette.length]);
        burst.appendChild(ray);
      }
      document.body.appendChild(burst);
      burst.addEventListener("animationend", () => burst.remove());

      const emoji = document.createElement("span");
      emoji.className = "spark-emoji";
      emoji.textContent = sparklePool[Math.floor(Math.random() * sparklePool.length)];
      emoji.style.left = `${event.clientX + 6}px`;
      emoji.style.top = `${event.clientY - 18}px`;
      document.body.appendChild(emoji);
      emoji.addEventListener("animationend", () => emoji.remove());
    });
  }

  /* ---------- 3D tilt + springy hover for cards ---------- */
  if (!reduceMotion) {
    document.querySelectorAll(".btn, .thumb-card, .feature-card, .stat-card").forEach((element) => {
      element.classList.add("motion-target");
      element.addEventListener("pointermove", (event) => {
        const rect = element.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        element.style.setProperty("--tilt-x", `${x * 6}deg`);
        element.style.setProperty("--tilt-y", `${y * -6}deg`);
      });
      element.addEventListener("pointerleave", () => {
        element.style.removeProperty("--tilt-x");
        element.style.removeProperty("--tilt-y");
        element.style.removeProperty("--lift");
      });
    });

    /* ---------- reveal on scroll (staggered) ---------- */
    const revealTargets = document.querySelectorAll(
      ".feature-card, .stat-card, .command-strip, .gallery-grid, .card, .filter-tabs"
    );
    revealTargets.forEach((element, index) => {
      element.classList.add("reveal-on-scroll");
      if (element.classList.contains("feature-card") || element.classList.contains("stat-card")) {
        element.style.setProperty("--reveal-delay", `${Math.min(index % 4, 3) * 0.09}s`);
      }
    });

    const pending = new Set();
    const reveal = (element) => {
      if (!pending.has(element)) return;
      pending.delete(element);
      element.classList.add("is-revealed");
      observer.unobserve(element);
    };
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) reveal(entry.target);
      });
    }, { threshold: 0.1, rootMargin: "0px 0px 120px 0px" });
    revealTargets.forEach((element) => {
      pending.add(element);
      observer.observe(element);
    });

    /* sweep fallback: reveal anything at or above the fold even after fast jumps */
    let sweepQueued = false;
    const sweep = () => {
      sweepQueued = false;
      const limit = window.innerHeight * 1.1;
      pending.forEach((element) => {
        if (element.getBoundingClientRect().top <= limit) reveal(element);
      });
    };
    window.addEventListener("scroll", () => {
      if (!sweepQueued && pending.size) {
        sweepQueued = true;
        requestAnimationFrame(sweep);
      }
    }, { passive: true });
    requestAnimationFrame(sweep);

    /* ---------- pop-in animation for every image once it loads ---------- */
    document.querySelectorAll("img").forEach((image) => {
      if (image.closest(".toon-stage, .mascot-dock, .toon-buddy, .doodle-layer")) return;
      const applyPop = () => {
        if (image.closest(".toon-stage, .mascot-dock, .toon-buddy, .doodle-layer")) return;
        image.classList.add("img-pop");
      };
      if (image.complete && image.naturalWidth > 0) applyPop();
      else image.addEventListener("load", applyPop);
    });

    /* ---------- flying cartoon characters ---------- */
    const rocket = document.getElementById("toon-rocket");
    const ufo = document.getElementById("toon-ufo");
    const launch = (flyer, delay, period) => {
      if (!flyer) return;
      const loop = () => {
        flyer.classList.remove("is-flying");
        void flyer.offsetWidth; /* restart CSS animation */
        flyer.classList.add("is-flying");
        flyer.addEventListener("animationend", () => {
          flyer.classList.remove("is-flying");
        }, { once: true });
      };
      setTimeout(loop, delay);
      setInterval(loop, period);
    };
    launch(rocket, 2500, 26000);
    launch(ufo, 11000, 34000);

    /* ---------- buddy bubble chatter ---------- */
    let buddyIndex = 0;
    setInterval(() => {
      if (document.hidden || buddy.matches(":hover")) return;
      sayTo(buddyBubble, buddyLines[buddyIndex % buddyLines.length]);
      buddyIndex += 1;
      buddy.classList.add("is-spinning");
      setTimeout(() => buddy.classList.remove("is-spinning"), 850);
    }, 12000);
  }

  /* ---------- mascot reactions (works with or without motion prefs) ---------- */
  mascot.addEventListener("mouseenter", () => {
    mascot.classList.add("is-talking");
    if (message) message.textContent = mascotLines[Math.floor(Math.random() * mascotLines.length)];
  });
  mascot.addEventListener("mouseleave", () => mascot.classList.remove("is-talking"));

  buddy.addEventListener("mouseenter", () => {
    buddy.classList.add("is-spinning");
    sayTo(buddyBubble, buddyLines[Math.floor(Math.random() * buddyLines.length)]);
    setTimeout(() => buddy.classList.remove("is-spinning"), 850);
  });

  /* emoji fountain used by clicks and celebrations */
  const emojiFountain = (x, y, count) => {
    if (reduceMotion) return;
    for (let i = 0; i < count; i += 1) {
      const emoji = document.createElement("span");
      emoji.className = "spark-emoji";
      emoji.textContent = sparklePool[Math.floor(Math.random() * sparklePool.length)];
      emoji.style.left = `${x + (Math.random() * 90 - 45)}px`;
      emoji.style.top = `${y - Math.random() * 24}px`;
      emoji.style.animationDelay = `${i * 0.09}s`;
      document.body.appendChild(emoji);
      emoji.addEventListener("animationend", () => emoji.remove());
    }
  };

  /* celebrate when a processing result lands (dispatch "vf:celebrate" anywhere) */
  window.addEventListener("vf:celebrate", () => {
    mascot.classList.add("is-happy");
    sayTo(message, "Image processed! Looking sharp! 🎉");
    setTimeout(() => mascot.classList.remove("is-happy"), 1300);
    sayTo(buddyBubble, "Wow, what a result! ✨");
    buddy.classList.add("is-spinning");
    setTimeout(() => buddy.classList.remove("is-spinning"), 850);
    const rect = buddy.getBoundingClientRect();
    emojiFountain(rect.left + rect.width / 2, rect.top, 14);
    emojiFountain(window.innerWidth / 2, window.innerHeight / 2, 10);
  });
})();
