"""
Video-KYC identity-consistency detector (docs/TECHNICAL_SPEC.md Section 4c,
Section 5's "Video-KYC identity-consistency detector... pretrained inference,
evaluated ourselves" row) -- the video counterpart to voice_spoof_detector.py
and document_consistency_detector.py, same Principle 6 rationale (pretrained
inference only, no training) and same Principle 13 shape (score() and
score_with_evidence() take only file paths, never is_fraud or the ground-
truth impostor_customer_id that generate_video_kyc_attacks.py records).

What this detects: whether the face(s) appearing in a submitted KYC video
match the claimed customer's own registered reference photo -- i.e. the
"identity" signal (TECHNICAL_SPEC Section 4b), NOT manipulation-artifact
detection (compression/blending/GAN artifacts from a synthetic swap). Those
are two structurally different questions. This project's attack cases
(generate_video_kyc_attacks.py) never use a face-swap/reenactment tool --
Kling's motion_control was considered and dropped because that capability
is policy-restricted even against synthetic identities -- so every attack
here is a genuinely different (synthetic) person's own unmodified video
submitted under a false claim. See that script's docstring for why a
deliberately-chosen, visually-similar impostor (the held_out tier) can
legitimately raise this detector's similarity score and lower its recall
compared to an arbitrarily-paired impostor (the train tier) -- that gap is
a real evaluation finding, not a bug. Frame-level GAN/diffusion artifact
detection (FaceForensics++/DFDC/Celeb-DF style pretrained checkpoints)
would only become relevant if a genuine synthetic-manipulation attack were
ever added to this family, and remains a documented future option, not
built here.

Uses facenet-pytorch (MIT license): MTCNN for face detection+alignment,
InceptionResnetV1 pretrained on VGGFace2 for face-embedding extraction.
Identity mismatch is 1 - mean cosine similarity between the reference
photo's embedding and each sampled video frame's embedding (clipped to
[0, 1] -- facenet-pytorch's VGGFace2 embeddings are not bounded to [-1, 1]
in practice for arbitrary face pairs, but same-identity cosine similarity
is reliably well above 0 and different-identity pairs cluster near or
below 0, so clipping loses no real signal and keeps the score interpretable
as a fraction).

Frame sampling via OpenCV (cv2 -- already a transitive dependency of this
project via document_consistency_detector.py's QR decoding), not a heavier
video library: N evenly-spaced frames across the clip's duration is enough
to average out a handful of blinks/occlusions/motion blur without needing
to decode every frame.

NOT executable in the cloud sandbox this was authored in -- depends on
facenet-pytorch/torch and real reference photos + video files that don't
exist in this repo yet (generate_video_kyc_attacks.py explains exactly
what's missing and where it needs to go).
"""

from pathlib import Path

import numpy as np

DEFAULT_N_FRAMES = 8


class VideoKycDetector:
    """Lazy-loads MTCNN + InceptionResnetV1 on first use (not at import
    time), matching DocumentConsistencyDetector._ensure_loaded()'s pattern
    -- importing this module doesn't require facenet-pytorch/torch unless
    the detector is actually used."""

    def __init__(self, n_frames: int = DEFAULT_N_FRAMES):
        self.n_frames = n_frames
        self._mtcnn = None
        self._resnet = None
        self._device = None

    def _ensure_loaded(self) -> None:
        if self._resnet is not None:
            return
        import torch
        from facenet_pytorch import MTCNN, InceptionResnetV1

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        # keep_all=False: KYC submission is single-subject by construction
        # (both bonafide and attack cases show exactly one claimed identity
        # at a time) -- take the highest-confidence face per frame, not a
        # list of all faces detected.
        self._mtcnn = MTCNN(image_size=160, margin=0, keep_all=False, device=self._device)
        self._resnet = InceptionResnetV1(pretrained="vggface2").eval().to(self._device)

    def _embed(self, img) -> "np.ndarray | None":
        """img: PIL Image or HxWx3 RGB ndarray. Returns a 512-d embedding,
        or None if no face was detected in this image/frame."""
        import torch

        face = self._mtcnn(img)
        if face is None:
            return None
        with torch.no_grad():
            embedding = self._resnet(face.unsqueeze(0).to(self._device))
        return embedding.detach().cpu().numpy()[0]

    def _embed_reference_photo(self, reference_photo_path) -> "np.ndarray | None":
        from PIL import Image

        img = Image.open(str(reference_photo_path)).convert("RGB")
        return self._embed(img)

    def _sample_frames(self, video_path) -> list:
        """Returns up to self.n_frames RGB ndarrays, evenly spaced across
        the clip. Fewer than requested if the video has fewer decodable
        frames than that -- never raises for a short clip."""
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            cap.release()
            raise FileNotFoundError(f"OpenCV could not open video file: {video_path}")
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            # Some codecs/containers don't report a reliable frame count
            # via CAP_PROP_FRAME_COUNT -- fall back to reading sequentially
            # and sampling every k-th decoded frame instead of seeking.
            frames = []
            ok, frame_bgr = cap.read()
            i = 0
            while ok:
                frames.append((i, frame_bgr))
                ok, frame_bgr = cap.read()
                i += 1
            cap.release()
            if not frames:
                return []
            idx = np.linspace(0, len(frames) - 1, num=min(self.n_frames, len(frames)), dtype=int)
            import cv2 as _cv2
            return [_cv2.cvtColor(frames[i][1], _cv2.COLOR_BGR2RGB) for i in idx]

        indices = np.linspace(0, frame_count - 1, num=min(self.n_frames, frame_count), dtype=int)
        out = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame_bgr = cap.read()
            if ok:
                out.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        cap.release()
        return out

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def score(self, video_path: str | Path, reference_photo_path: str | Path) -> float:
        score, _evidence = self.score_with_evidence(video_path, reference_photo_path)
        return score

    def score_with_evidence(self, video_path: str | Path, reference_photo_path: str | Path) -> tuple:
        """Returns (identity_mismatch_score in [0, 1], evidence: list[str]).
        Principle 13: takes only the video and the claimed customer's own
        registered reference photo -- never is_fraud, never which customer
        the video's face actually belongs to.

        0.5 ("genuinely unknown") is returned, same convention as
        DocumentConsistencyDetector, when no face can be extracted from the
        reference photo or from any sampled video frame -- that is a real,
        different failure mode from "faces detected but they don't match",
        and collapsing it to either 0.0 or 1.0 would misrepresent it as
        evidence of bonafide-ness or fraud."""
        self._ensure_loaded()

        ref_embedding = self._embed_reference_photo(reference_photo_path)
        if ref_embedding is None:
            return 0.5, [f"No face detected in reference photo ({Path(reference_photo_path).name}) "
                          f"-- score is genuinely unknown"]

        frames = self._sample_frames(video_path)
        if not frames:
            return 0.5, [f"No frames could be decoded from video ({Path(video_path).name}) "
                          f"-- score is genuinely unknown"]

        similarities = []
        evidence = []
        for i, frame in enumerate(frames):
            emb = self._embed(frame)
            if emb is None:
                evidence.append(f"frame {i}/{len(frames)}: no face detected, skipped")
                continue
            sim = self._cosine_similarity(emb, ref_embedding)
            similarities.append(sim)
            evidence.append(f"frame {i}/{len(frames)}: cosine_similarity_to_reference={sim:.4f}")

        if not similarities:
            evidence.insert(0, "No face detected in any sampled video frame -- score is genuinely unknown")
            return 0.5, evidence

        mean_sim = float(np.mean(similarities))
        score = float(np.clip(1.0 - mean_sim, 0.0, 1.0))
        evidence.append(
            f"mean_cosine_similarity={mean_sim:.4f} across {len(similarities)}/{len(frames)} "
            f"sampled frames with a detected face"
        )
        evidence.append(f"identity_mismatch_score={score:.4f}")
        return score, evidence

    def score_batch(self, pairs: list) -> np.ndarray:
        """pairs: list of (video_path, reference_photo_path) tuples -- each
        case supplies its own claimed customer's reference photo (unlike
        voice_spoof_detector's single-input score_batch, identity checking
        is inherently a two-input comparison, not a standalone clip
        property)."""
        return np.array([self.score(v, r) for v, r in pairs], dtype="float64")
