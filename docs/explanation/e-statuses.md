# Charm Statuses

> :warning: **WARNING** : it is an work-in-progress article. Do NOT use it in production! Contact [Canonical Data Platform team](https://chat.charmhub.io/charmhub/channels/data-platform) if you are interested in the topic.

The charm follows [standard Juju applications statuses](https://juju.is/docs/olm/status-values#heading--application-status). Here you can find the expected end-users reaction on different statuses:

| Juju Status | Message | Expectations | Actions |
|-------|-------|-------|-------|
| **active** | any | Normal charm operations | No actions required |
| **waiting** | any | Charm is waiting for relations to be finished | No actions required |
| **maintenance** | any | Charm is performing the internal maintenance (e.g. re-configuration) | No actions required |
| **blocked** | any | The manual user activity is required! | Follow the message hints (see below) |
| **blocked** | waiting for backend database relation to initialise  | Normal behavior, charm needs all relations to work. | Follow the hint to establish a proper relation. |
| **error** | any | An unhanded internal error happened | Read the message hint. Execute `juju resolve <error_unit/0>` after addressing the root of the error state |
| **terminated** | any | The unit is gone and will be cleaned by Juju soon | No actions possible |
| **unknown** | any | Juju doesn't know the charm app/unit status. Possible reason: K8s charm termination in progress. | Manual investigation required if status is permanent |