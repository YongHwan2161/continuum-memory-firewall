from pathlib import Path


WORKFLOWS = Path(__file__).parents[1] / ".github" / "workflows"
EXPECTED_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/configure-pages": "45bfe0192ca1faeb007ade9deae92b16b8254a0d",
    "actions/deploy-pages": "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
    "actions/upload-pages-artifact": "fc324d3547104276b827a68afc52ff2a11cc49c9",
}


def test_node24_actions_are_immutable_and_uniform() -> None:
    occurrences = {action: [] for action in EXPECTED_PINS}

    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for action, expected_sha in EXPECTED_PINS.items():
                marker = f"{action}@"
                if marker not in line:
                    continue
                actual_ref = line.split(marker, 1)[1].split()[0]
                occurrences[action].append((workflow.name, line_number))
                assert len(actual_ref) == 40 and all(
                    character in "0123456789abcdef" for character in actual_ref
                ), f"{workflow}:{line_number} contains an incomplete commit SHA"
                assert actual_ref == expected_sha, (
                    f"{workflow}:{line_number} must pin {action} to the reviewed "
                    f"Node 24 commit {expected_sha}, got {actual_ref}"
                )

    assert all(occurrences.values()), f"missing action coverage: {occurrences}"
