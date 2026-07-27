from render_job import RenderJob, RenderStatus


class RenderQueue:
    """Manage an ordered, sequential collection of render jobs."""

    def __init__(self):
        self.jobs = []

    @property
    def active_job(self):
        """Return the currently rendering job, if there is one."""

        for job in self.jobs:
            if job.status == RenderStatus.RENDERING:
                return job

        return None

    def add(self, job):
        """Add a waiting job to the end of the queue."""

        if not isinstance(job, RenderJob):
            raise TypeError(
                "Only RenderJob objects can be queued."
            )

        if self.get(job.job_id) is not None:
            raise ValueError(
                "This render job is already queued."
            )

        job.mark_waiting()
        self.jobs.append(job)

    def get(self, job_id):
        """Find a job by its unique identifier."""

        for job in self.jobs:
            if job.job_id == job_id:
                return job

        return None

    def remove(self, job_id):
        """Remove a job unless it is currently rendering."""

        job = self.get(job_id)

        if job is None:
            return False

        if job.status == RenderStatus.RENDERING:
            raise ValueError(
                "The active render cannot be removed."
            )

        self.jobs.remove(job)
        return True

    def next_waiting_job(self):
        """Return the first waiting job."""

        for job in self.jobs:
            if job.status == RenderStatus.WAITING:
                return job

        return None

    def move_to_next(self, job_id):
        """
        Move a waiting job directly behind the active render.

        If the queue is idle, move it to the beginning instead.
        """

        job = self.get(job_id)

        if job is None:
            raise ValueError(
                "The selected render job does not exist."
            )

        if job.status != RenderStatus.WAITING:
            raise ValueError(
                "Only waiting jobs can be moved."
            )

        self.jobs.remove(job)

        active_job = self.active_job

        if active_job is None:
            self.jobs.insert(0, job)
            return

        active_index = self.jobs.index(
            active_job
        )

        self.jobs.insert(
            active_index + 1,
            job,
        )

    def start_job(self, job):
        """Mark one waiting job as the active render."""

        if job not in self.jobs:
            raise ValueError(
                "The render job is not in this queue."
            )

        if self.active_job is not None:
            raise ValueError(
                "Another video is already rendering."
            )

        if job.status != RenderStatus.WAITING:
            raise ValueError(
                "Only waiting jobs can be started."
            )

        job.mark_rendering()

    def clear_completed(self):
        """Remove completed jobs while keeping all other jobs."""

        self.jobs = [
            job
            for job in self.jobs
            if job.status != RenderStatus.COMPLETED
        ]

    def waiting_count(self):
        return sum(
            job.status == RenderStatus.WAITING
            for job in self.jobs
        )

    def completed_count(self):
        return sum(
            job.status == RenderStatus.COMPLETED
            for job in self.jobs
        )