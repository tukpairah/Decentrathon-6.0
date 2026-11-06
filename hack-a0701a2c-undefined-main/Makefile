predict:
	python -m app.predict --inp $(IN) --out $(OUT)

serve:
	uvicorn app.main:app --reload

test:
	pytest -q

eval-stub:
	python -m evaluation.stub_server

eval:
	python -m evaluation.run_eval

eval-latency:
	python -m evaluation.run_eval --workers 1 --n 200

eval-gold:
	python -m evaluation.run_eval --gold gold.jsonl

eval-cost:
	python -m evaluation.cost --pred $$(ls -d results/*/ | tail -1)pred.jsonl

.PHONY: eval-stub eval eval-latency eval-gold eval-cost
