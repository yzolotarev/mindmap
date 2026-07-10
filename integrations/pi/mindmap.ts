/**
 * Mindmap — Pi Extension (v7 — умный триггер + GRINDE)
 *
 * Схема по Джастину Сангу (connect-the-dots): агент раскладывает тему на
 * изолированные объекты, юзер САМ соединяет их на канвасе (encoding, Bloom 3-5),
 * агент проверяет по GRINDE и углубляет слоями (Layer 1 → 2).
 *
 * 1. Декомпозиция → SCENE_FILE + канвас + ASCII
 * 2. Следующий любой ввод → если export не пуст → разбор результата
 * 3. В режиме on перехватываются ТОЛЬКО объяснительные запросы
 *    («объясни», «как работает», «хочу чтобы...») — не любой ввод
 *
 * /mindmap (on|off|status)  /mindmap <тема>  /schem <тема>
 */

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { join } from "node:path";

const HOME = process.env.HOME || "/home/y";
const STATE_FILE = HOME + "/.pi/agent/mindmap.state";
const CANVAS = HOME + "/bin/mindmap-canvas.py";
const SCENE_FILE = "/tmp/mindmap-scene.txt";
const EXPORT_FILE = "/tmp/mindmap-export.txt";

// Триггер «нужного момента»: юзер просит объяснить ИЛИ объясняет сам, как должно работать
const TRIGGER = /объясни|расскажи про|что такое|как (это |оно )?работает|как устроен|почему|разбер[ёе]мся|разбери|не понимаю|не понял|принцип работы|схем[ау]|хочу чтобы|должно работать|я себе представляю|вот как я вижу/i;

function enabled(): boolean {
	try { return readFileSync(STATE_FILE, "utf-8").trim() === "on"; }
	catch { return false; }
}

export default function (pi: any) {
	let on = enabled();

	function setOn(v: boolean, ctx: any) {
		on = v;
		try { writeFileSync(STATE_FILE, v ? "on" : "off", "utf-8"); } catch {}
		ctx.ui.notify(v ? "Mindmap: ВКЛ" : "Mindmap: ВЫКЛ", "info");
	}

	async function phase1(prompt: string, ctx: any) {
		let scene = "", nodes: string[] = [];

		// try graphify
		const gd = (() => {
			const d = join(process.cwd(), "graphify-out");
			return existsSync(join(d, "GRAPH_REPORT.md")) ? d : null;
		})();
		if (gd && existsSync(join(gd, "graph.json"))) {
			try {
				const data = JSON.parse(readFileSync(join(gd, "graph.json"), "utf-8"));
				const raw: any[] = data.nodes || data.elements || [];
				nodes = raw.map((n: any) => n.name || n.label || "").filter(Boolean).slice(0, 12);
			} catch {}
		}
		if (nodes.length < 3) {
			try {
				const r = await fetch("http://localhost:8081/v1/chat/completions", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						model: "gemini-3.5-flash", temperature: 0.4,
						messages: [
							{ role: "system", content:
								"Ты декомпозируешь тему для connect-the-dots схемы (метод Джастина Санга, Layer 1). " +
								"Выдели 4-7 САМЫХ КРУПНЫХ объектов темы — не деталей (имя 1-3 слова, понятно 15-летнему; " +
								"жаргон замени бытовым словом). Объекты должны покрывать всю тему и быть соединимыми " +
								"причинно-следственными стрелками. К КАЖДОМУ объекту добавь одну бытовую фразу-объяснение " +
								"(она станет всплывающей подсказкой по наведению — не жалей на неё усилий, юзер её увидит, " +
								"когда не поймёт название). " +
								"Нарисуй 2D ASCII: объекты в ┌─┐, разбросаны по плоскости, НЕТ линий и стрелок. " +
								"После сцены строка __NODES__: Имя1 — фраза1::Имя2 — фраза2::Имя3 — фраза3" },
							{ role: "user", content: prompt },
						],
					}),
					signal: AbortSignal.timeout(35000),
				});
				const d: any = await r.json();
				const t = (d?.choices?.[0]?.message?.content || "").trim();
				const m = t.match(/__NODES__:\s*(.+)/);
				nodes = m ? m[1].split("::").map((s: string) => s.trim()).filter(Boolean) : [];
				scene = t.replace(/__NODES__:\s*.+[\r\n]?/, "").trim();
			} catch (e: any) {
				ctx.ui.notify("mindmap: Gemini ошибка " + e.message, "warning");
				return;
			}
		}
		if (!nodes.length) { ctx.ui.notify("mindmap: нет узлов", "warning"); return; }

		if (!scene) {
			const pos = [{x:0,y:0},{x:28,y:0},{x:14,y:4},{x:0,y:8},{x:28,y:8},{x:8,y:12},{x:24,y:12},{x:0,y:16},{x:28,y:16}];
			const ls: string[] = [];
			for (let i = 0; i < nodes.length; i++) {
				const n = nodes[i], p = pos[i % pos.length];
				const w = Math.max(n.length + 2, 12);
				if (ls.length <= p.y) ls.length = p.y + 3;
				const pad = " ".repeat(p.x);
				ls[p.y] = (ls[p.y]||"") + pad + "┌" + "─".repeat(w) + "┐";
				ls[p.y+1] = (ls[p.y+1]||"") + pad + "│ " + n.padEnd(w-2) + " │";
				ls[p.y+2] = (ls[p.y+2]||"") + pad + "└" + "─".repeat(w) + "┘";
			}
			scene = ls.filter(l => l !== undefined).join("\n");
		}

		try { writeFileSync(SCENE_FILE, scene, "utf-8"); writeFileSync(EXPORT_FILE, ""); } catch {}
		const title = prompt.slice(0, 40).replace(/\s+/g, " ").trim();
		spawn("python3", [CANVAS, "--nodes", nodes.join("::"), "--title", title], { detached: true, stdio: "ignore" }).unref();

		ctx.ui.notify("mindmap: " + nodes.length + " узлов", "info");
		return {
			message: {
				customType: "mindmap",
				content: "**MINDMAP**\n\n```\n" + scene + "\n```\n\nСоедини в окне и закрой — канвас сам отправит «готово», я прочитаю export.",
				display: true,
			},
		};
	}

	pi.on("before_agent_start", async (event: any, ctx: any) => {
		// Флаг: если scene есть и export не пуст — перехват ДО всего
		if (existsSync(SCENE_FILE)) {
			const exp = readFileSync(EXPORT_FILE, "utf-8").trim();
			if (exp) {
				const scene = readFileSync(SCENE_FILE, "utf-8").trim();
				try { writeFileSync(SCENE_FILE, ""); writeFileSync(EXPORT_FILE, ""); } catch {}
				ctx.ui.notify("mindmap: export", "info");
				return {
					message: {
						customType: "mindmap-result",
						content: "**MINDMAP — Результат**\n\nСоединения юзера:\n```\n" + exp + "\n```\n\n" +
							"Объекты, которые юзер пометил «?» (СКМ по объекту на канвасе) — переформулируй их проще " +
							"на следующей итерации, это сигнал непонятного слова, не ошибка связи. " +
							"НЕ рисуй диаграмму руками и НЕ пиши абзацы — юзер явно просил меньше текста (08.07.26). " +
							"Покажи правки в GUI: python3 ~/bin/mindmap-review.py --mark \"X-Y:add:причина,X-Y:wrong:причина\" " +
							"--ask \"X-Y:вопрос почему\" --title \"тема: правки\" " +
							"(макс 2 записи в --mark, остальное — в следующую итерацию). Откроется канвас с расположением юзера, его связи " +
							"как были, правки жёлтым пунктиром. Третье поле ОБЯЗАТЕЛЬНО: 2-4 слова ПОЧЕМУ — надпись на жёлтой " +
							"стрелке (не вердикт «верно»). add = не хватало, wrong = у юзера неверна (его линия не трогается). " +
							"--ask кладёт вопрос «почему?» про ключевую стрелку юзера ПРЯМО НА КАНВАС (оранжевый пунктирный узел " +
							"с линиями к обеим сторонам стрелки) вместо текста в чате. " +
							"Fallback без GUI: mindmap-ascii.py с теми же --mark. Каждую правку — ОДНОЙ бытовой фразой вида " +
							"«у тебя Канвас → Проверка, на самом деле Канвас → Агент: окно будит агента»; никаких " +
							"легенд, символов и буквенных кодов в тексте, только имена объектов словами. " +
							"Под картинкой продублируй ту же фразу и вопрос, который уже на канвасе. В конце (если тема закрыта) предложи: углубить группу (Layer 2) или " +
							"сохранить заметкой в Obsidian. Если связей нет / юзер написал «сдаюсь» — вызови скрипт с --mark для всех " +
							"недостающих рёбер сам.",
						display: true,
					},
				};
			}
		}

		const cmd = event.prompt.match(/^\/mindmap\s+(.+)/s);
		const schemCmd = event.prompt.match(/^\/schem\s+(.+)/s);
		if (cmd) return phase1(cmd[1].trim(), ctx);
		if (schemCmd) return phase1(schemCmd[1].trim(), ctx);
		// умный триггер: не любой ввод, а только «объясни мне» / «объясняю тебе как должно работать»
		if (on && event.prompt.trim().length >= 20 && !event.prompt.startsWith("/") && !event.prompt.startsWith("!")
			&& TRIGGER.test(event.prompt)) return phase1(event.prompt, ctx);
	});

	pi.registerCommand("mindmap", {
		description: "Mindmap — Connect-the-Dots. /mindmap on|off|status или /mindmap <тема>",
		handler: async (args: string, ctx: any) => {
			const a = (args||"").trim().toLowerCase();
			if ("off" === a || "0" === a || "false" === a) setOn(false, ctx);
			else if ("on" === a || "1" === a || "true" === a) setOn(true, ctx);
			else if (!a || "status" === a) ctx.ui.notify("Mindmap: " + (on ? "ВКЛ" : "ВЫКЛ"), "info");
			else return phase1(args!.trim(), ctx);
		},
	});

	pi.registerCommand("schem", {
		description: "Алиас: /schem <тема> — Connect-the-Dots с GUI-канвасом",
		handler: async (args: string, ctx: any) => {
			if (!(args||"").trim()) ctx.ui.notify("/schem <тема> — схема на канвасе", "info");
			else return phase1(args!.trim(), ctx);
		},
	});

	pi.on("session_start", (_e: any, ctx: any) => {
		ctx.ui.notify("Mindmap: " + (on ? "ВКЛ (/mindmap off)" : "ВЫКЛ (/mindmap on)"), "info");
	});
}
