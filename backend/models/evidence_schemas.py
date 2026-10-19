"""
Evidence Board & True Crime Schemas
-----------------------------------
Pydantic data models for the Investigation Corkboard Engine, Causal DAG,
Foreshadowing Ledger, and Fictionalized Case Plan.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EvidenceNode(BaseModel):
    """
    Represents an evidence card pinned to the Corkboard.
    Coordinates (x, y) are fixed permanently (Fixed-Anchor Grid Layout)
    so positions never shift across subsequent scenes.
    """
    id: str = Field(description="Unique node identifier, e.g., 'suspect_01', 'clue_knife'")
    label: str = Field(description="Display title or name on the evidence card")
    node_type: str = Field(
        default="clue",
        description="Type: 'suspect', 'victim', 'weapon', 'clue', 'location', 'forensic_report', 'timeline_event'"
    )
    description: str = Field(default="", description="Short summary of the evidence or role")
    image_path: Optional[str] = Field(default=None, description="Local path to card image")
    image_url: Optional[str] = Field(default=None, description="Web/static URL to card image")
    x: int = Field(default=960, description="Permanent X coordinate on 1920x1080 canvas")
    y: int = Field(default=540, description="Permanent Y coordinate on 1920x1080 canvas")
    pinned: bool = Field(default=True, description="Fixed-anchor flag; prevents recalculating coordinates")
    pin_color: str = Field(default="red", description="Pin head color: 'red', 'yellow', 'silver', 'blue'")
    status: str = Field(
        default="active",
        description="Status: 'active', 'suspect', 'alibi', 'confirmed', 'deceased', 'cleared', 'eliminated'"
    )
    stamp: Optional[str] = Field(
        default=None,
        description="Rubber stamp overlay: 'ALIBI', 'CONFIRMED', 'ELIMINATED', 'DECEASED', 'X', or None"
    )
    appearance_scene_order: int = Field(
        default=1,
        description="The scene number (1-based) where this node first appears on the board"
    )
    rotation_deg: float = Field(
        default=0.0,
        description="Subtle permanent tilt angle in degrees (-4.0 to +4.0) for natural polaroid look"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata")


class RelationEdge(BaseModel):
    """
    Represents a red thread (yarn) connecting two pinned evidence nodes.
    Drawn as a natural sagging Bezier curve simulating gravity.
    """
    id: str = Field(description="Unique edge identifier, e.g., 'edge_s1_victim'")
    source_id: str = Field(description="Source EvidenceNode id (origin pin)")
    target_id: str = Field(description="Target EvidenceNode id (destination pin)")
    relation_type: str = Field(
        default="suspect_link",
        description="Semantic link: 'motive', 'alibi_contradiction', 'blood_match', 'call_log', 'witness_seen', 'suspect_link', 'causal', 'timeline'"
    )
    label: Optional[str] = Field(default=None, description="Optional brief label on the thread tag")
    color: str = Field(default="#dc2626", description="Thread color (default crimson red)")
    style: str = Field(
        default="sagging_bezier",
        description="Visual render style: 'sagging_bezier', 'solid', 'dashed'"
    )
    appearance_scene_order: int = Field(
        default=1,
        description="The scene number (1-based) where this red thread is pinned"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary edge metadata")


class BoardState(BaseModel):
    """
    Snapshot of the Investigation Corkboard at scene K.
    Demonstrates cumulative progression: Scene K only displays nodes and edges
    revealed up to time K (Cumulative State = DeltaNodes_k + DeltaEdges_k).
    """
    scene_order: int = Field(description="Current scene index (1-based)")
    title: str = Field(default="Investigation Board", description="Board stage header")
    cumulative_nodes: List[EvidenceNode] = Field(
        default_factory=list,
        description="All nodes visible up to this scene"
    )
    cumulative_edges: List[RelationEdge] = Field(
        default_factory=list,
        description="All edges visible up to this scene"
    )
    delta_nodes: List[EvidenceNode] = Field(
        default_factory=list,
        description="Newly revealed nodes specifically in this scene"
    )
    delta_edges: List[RelationEdge] = Field(
        default_factory=list,
        description="Newly pinned threads specifically in this scene"
    )
    canvas_width: int = Field(default=1920)
    canvas_height: int = Field(default=1080)
    render_image_path: Optional[str] = Field(default=None, description="Path to rendered static 1080p JPG/PNG")
    render_video_path: Optional[str] = Field(default=None, description="Path to rendered 5s dynamic MP4 clip")


class ForeshadowingItem(BaseModel):
    """
    Manages foreshadowing clue lifecycle:
    Planted -> Triggered (optional) -> Resolved/Payout.
    Guarantees no orphaned clues remain unresolved in the script.
    """
    id: str = Field(description="Unique clue identifier, e.g., 'clue_umbrella'")
    clue_name: str = Field(description="Name or title of the foreshadowed detail")
    planted_scene_order: int = Field(description="Scene number where clue is first planted")
    triggered_scene_order: Optional[int] = Field(
        default=None,
        description="Scene number where clue is noticed or raised as a question"
    )
    resolved_scene_order: Optional[int] = Field(
        default=None,
        description="Scene number where clue's true significance is unmasked"
    )
    status: str = Field(
        default="planted",
        description="Lifecycle state: 'planted', 'triggered', 'resolved'"
    )
    description: str = Field(description="What the clue is and its surface appearance")
    payout_explanation: Optional[str] = Field(
        default=None,
        description="How this clue directly cracks the case or unmasks the culprit"
    )


class FictionalCasePlan(BaseModel):
    """
    Complete Master Plan for an adapted True Crime episode.
    Implements 70% Real Forensic Truth + 30% Suspense / Red Herring Fictionalization.
    """
    case_id: str = Field(description="Unique case code, e.g., 'case_cang_tan_hai'")
    title: str = Field(description="Fictionalized episode title")
    original_summary: Optional[str] = Field(default=None, description="Original raw report summary")
    alias_vault: Dict[str, str] = Field(
        default_factory=dict,
        description="Deterministic 1-to-1 PII anonymization mapping: Real Name -> Fictional Alias"
    )
    truth_ratio: float = Field(default=0.7, description="Forensic truth proportion (default 70%)")
    fiction_ratio: float = Field(default=0.3, description="Suspense/Red Herring proportion (default 30%)")
    nodes: List[EvidenceNode] = Field(
        default_factory=list,
        description="All nodes with permanent fixed-anchor coordinates"
    )
    edges: List[RelationEdge] = Field(
        default_factory=list,
        description="All causal and suspect relation threads"
    )
    foreshadowing_ledger: List[ForeshadowingItem] = Field(
        default_factory=list,
        description="Tracked foreshadowing items across scenes"
    )
    board_states: List[BoardState] = Field(
        default_factory=list,
        description="Cumulative board state per scene"
    )
    scenes_script: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="5s scene script items with A-Roll (Noir Silhouette) and B-Roll (Evidence Board)"
    )
