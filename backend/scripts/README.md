# MediAgent Backend Scripts

This directory contains utility scripts for testing, verification, and benchmarking.

---

## MedGemma Integration Scripts

### 1. verify_medgemma_setup.py

Quick verification that MedGemma is configured correctly.

```bash
python3 backend/scripts/verify_medgemma_setup.py
```

**Checks:**
- MedGemmaClient imports successfully
- HUGGINGFACE_API_TOKEN is configured
- Client initializes properly
- Available models
- Interface compatibility

**Expected Output:**
```
✅ MedGemma is ready to use with Hugging Face API!
```

---

### 2. test_medgemma_hf.py

Comprehensive integration tests for MedGemma via Hugging Face API.

```bash
python3 backend/scripts/test_medgemma_hf.py
```

**Tests:**
1. Basic medical question
2. Generation with system instruction
3. Medical lab result explanation
4. Adverse drug reaction detection
5. Model size comparison

**Expected Output:**
```
🎉 All tests PASSED!
```

**Note:** First request may take 10-30 seconds while model loads.

---

### 3. compare_medgemma_gemini.py

Side-by-side comparison of MedGemma vs Gemini on medical tasks.

```bash
python3 backend/scripts/compare_medgemma_gemini.py
```

**Compares:**
- Response quality
- Response time
- Response length
- Medical accuracy (manual review needed)

**Test Cases:**
1. Basic medical question
2. Lab result explanation
3. Adverse drug reaction detection
4. Medication question

**Expected Output:**
```
✅ Comparison complete!
```

---

## Usage Examples

### Quick Start

```bash
# 1. Verify setup
python3 backend/scripts/verify_medgemma_setup.py

# 2. Run integration tests
python3 backend/scripts/test_medgemma_hf.py

# 3. Compare with Gemini
python3 backend/scripts/compare_medgemma_gemini.py
```

### Prerequisites

1. **Hugging Face API Token**
   - Get from: https://huggingface.co/settings/tokens
   - Add to `.env`: `HUGGINGFACE_API_TOKEN=hf_...`
   - Accept terms at: https://huggingface.co/google/medgemma-4b-it

2. **Google API Key** (for Gemini comparison)
   - Get from: https://aistudio.google.com/app/apikey
   - Add to `.env`: `GOOGLE_API_KEY=...`

3. **Python Dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

---

## Troubleshooting

### "HUGGINGFACE_API_TOKEN not set"

**Solution:**
1. Create Hugging Face account
2. Get API token from settings
3. Add to `.env` file
4. Restart application

### "Model is loading" (503 error)

**Solution:**
- Wait 10-30 seconds
- Scripts automatically retry
- Normal for first request or after inactivity

### "Rate limit exceeded"

**Solution:**
- Wait a few minutes
- Reduce request frequency
- Free tier: ~1000 requests/day, ~10 requests/minute

### "Empty response from MedGemma"

**Solution:**
- Check prompt format
- Increase max_tokens parameter
- Try different model size

---

## Performance Notes

### Model Loading Time

First request may take 10-30 seconds while HF loads the model into memory. Subsequent requests are fast.

### Expected Latency

- `medgemma-1.5-4b-it`: 1-3 seconds
- `medgemma-4b-it`: 2-5 seconds
- `medgemma-27b-it`: 5-15 seconds
- `gemini-2.0-flash-exp`: 0.5-2 seconds

### Rate Limits (Free Tier)

- ~1000 requests/day
- ~10 requests/minute
- Sufficient for testing and benchmarking

---

## Next Steps

After running these scripts:

1. **Review Responses**
   - Compare MedGemma vs Gemini quality
   - Have medical experts evaluate accuracy
   - Check for hallucinations

2. **Create Golden Test Sets**
   - 50 lab reports with expert explanations
   - 30 discharge summaries
   - 100 symptom reports
   - 50 ADR cases
   - 100 medical Q&A pairs

3. **Implement Benchmarking Framework**
   - Automated testing
   - Metrics collection
   - Report generation

4. **Run Formal Benchmarks**
   - Accuracy measurement
   - Latency measurement
   - Cost analysis
   - Make model selection decision

---

## References

- [MedGemma Documentation](https://developers.google.com/health-ai-developer-foundations/medgemma)
- [Hugging Face Inference API](https://huggingface.co/docs/api-inference/index)
- [Implementation Guide](../docs/MEDGEMMA_HF_IMPLEMENTATION.md)
- [Integration Plan](../docs/MEDGEMMA_INTEGRATION_PLAN.md)
